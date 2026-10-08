import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import FRONTEND_URL
from app.core.security import create_access_token, decode_access_token
from app.models.nguoi_dung import NguoiDung
from app.models.revoked_token import RevokedToken
from app.models.token_mat_khau import TokenMatKhau
from app.models.token_kich_hoat import TokenKichHoat
from app.schemas.forgot_password import ForgotPasswordRequest
from app.schemas.login import LoginRequest
from app.schemas.admin_create_user import AdminCreateUserRequest
from app.schemas.nguoi_dung import NguoiDungCreate, NguoiDungLock
from app.schemas.register import RegisterRequest
from app.schemas.reset_password import ResetPasswordRequest
from app.services.email_service import (
    send_reset_password_email,
    send_activation_email,
)


password_hash = PasswordHash.recommended()
logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ============================================================
# SINH MẬT KHẨU TẠM THỜI
# ============================================================

def generate_temporary_password(length: int = 12) -> str:
    """
    Sinh mật khẩu tạm thời ngẫu nhiên.

    Mật khẩu luôn có:
    - chữ thường
    - chữ hoa
    - chữ số
    """

    if length < 3:
        raise ValueError(
            "Độ dài mật khẩu tạm thời phải từ 3 ký tự"
        )

    lowercase = "abcdefghijklmnopqrstuvwxyz"
    uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = "0123456789"

    password = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
    ]

    all_characters = lowercase + uppercase + digits

    password.extend(
        secrets.choice(all_characters)
        for _ in range(length - 3)
    )

    secrets.SystemRandom().shuffle(password)

    return "".join(password)


# ============================================================
# USER DATA
# ============================================================

def _user_data(user: NguoiDung) -> dict:
    return {
        "nguoiDungId": user.NguoiDungId,
        "hoTen": user.HoTen,
        "email": user.Email,
        "trangThai": user.TrangThai,
    }


# ============================================================
# TÌM USER
# ============================================================

def _find_user(
    db: Session,
    user_id: int,
) -> NguoiDung:

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId == user_id
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng",
        )

    return user


# ============================================================
# ĐĂNG KÝ USER
# ============================================================

def register_user(
    db: Session,
    request: RegisterRequest,
):
    email = str(request.email).strip().lower()

    existing_user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email đã được sử dụng",
        )

    now = datetime.now()

    user = NguoiDung(
        HoTen=request.ho_ten.strip(),
        Email=email,
        SoDienThoai=(
            request.so_dien_thoai.strip()
            if request.so_dien_thoai
            else None
        ),
        MatKhauHash=password_hash.hash(
            request.password
        ),
        TrangThai="HoatDong",
        BatBuocDoiMatKhau=False,
        CanDoiMatKhau=False,
        MatKhauTamThoiHetHan=None,
        SoLanDangNhapSai=0,
        KhoaDen=None,
        LyDoKhoa=None,
        NgayTao=now,
        NgayCapNhat=now,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể tạo tài khoản",
        )

    return {
        "message": "Đăng ký thành công",
        "user": _user_data(user),
    }


# ============================================================
# TẠO USER THÔNG THƯỜNG
# ============================================================

def create_user(
    db: Session,
    request: NguoiDungCreate,
):
    email = str(request.email).strip().lower()

    exists = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    if exists:
        raise HTTPException(
            status_code=400,
            detail="Email đã được sử dụng",
        )

    now = datetime.now()

    user = NguoiDung(
        HoTen=request.ho_ten.strip(),
        Email=email,
        SoDienThoai=request.so_dien_thoai,
        MatKhauHash=password_hash.hash(
            request.password
        ),
        TrangThai="HoatDong",
        BatBuocDoiMatKhau=False,
        CanDoiMatKhau=False,
        MatKhauTamThoiHetHan=None,
        SoLanDangNhapSai=0,
        KhoaDen=None,
        LyDoKhoa=None,
        TokenValidAfter=None,
        NgayTao=now,
        NgayCapNhat=now,
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể tạo người dùng",
        )

    return {
        "message": "Tạo người dùng thành công",
        "user": _user_data(user),
    }


# ============================================================
# ADMIN TẠO TÀI KHOẢN
# ============================================================

def admin_create_user(
    db: Session,
    request: AdminCreateUserRequest,
):
    """
    Admin tạo tài khoản người dùng.

    Admin chỉ nhập:
    - Họ tên
    - Email
    - Vai trò

    Backend tự:
    - Kiểm tra email
    - Kiểm tra vai trò
    - Sinh mật khẩu tạm thời
    - Hash mật khẩu
    - Đánh dấu bắt buộc đổi mật khẩu
    - Đặt hạn mật khẩu tạm thời 24 giờ
    - Tạo token kích hoạt
    - Gán đúng VaiTroId
    - Gửi email cho người dùng
    """

    email = str(request.email).strip().lower()
    ho_ten = request.ho_ten.strip()

    # ========================================================
    # 1. VALIDATE HỌ TÊN
    # ========================================================

    if not ho_ten:
        raise HTTPException(
            status_code=400,
            detail="Họ tên không được để trống",
        )

    # ========================================================
    # 2. LẤY CHÍNH XÁC VAI TRÒ ĐƯỢC CHỌN
    # ========================================================

    try:
        selected_role_id = int(request.vai_tro_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Vai trò không hợp lệ",
        )

    if selected_role_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Vai trò không hợp lệ",
        )

    # ========================================================
    # 3. KIỂM TRA EMAIL ĐÃ TỒN TẠI
    # ========================================================

    existing_user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email đã tồn tại",
        )

    # ========================================================
    # 4. KIỂM TRA VAI TRÒ
    #
    # QUAN TRỌNG:
    # Luôn truy vấn theo đúng selected_role_id.
    # Không dùng index của danh sách vai trò.
    # ========================================================

    role = db.execute(
        text("""
            SELECT
                VaiTroId,
                TenVaiTro
            FROM VaiTro
            WHERE VaiTroId = :vai_tro_id
        """),
        {
            "vai_tro_id": selected_role_id,
        },
    ).mappings().first()

    if not role:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Vai trò có ID {selected_role_id} "
                "không tồn tại"
            ),
        )

    # Kiểm tra thêm để chắc chắn DB trả đúng ID
    database_role_id = int(role["VaiTroId"])

    if database_role_id != selected_role_id:
        raise HTTPException(
            status_code=500,
            detail=(
                "ID vai trò được chọn không khớp "
                "với dữ liệu trong cơ sở dữ liệu"
            ),
        )

    # ========================================================
    # 5. SINH MẬT KHẨU TẠM THỜI
    # ========================================================

    temporary_password = generate_temporary_password()

    # ========================================================
    # 6. THỜI GIAN
    # ========================================================

    now = datetime.now()

    temporary_password_expiry = (
        now + timedelta(hours=24)
    )

    # ========================================================
    # 7. TẠO USER
    # ========================================================

    user = NguoiDung(
        HoTen=ho_ten,
        Email=email,
        SoDienThoai=None,
        MatKhauHash=password_hash.hash(
            temporary_password
        ),
        TrangThai="HoatDong",

        # Chưa kích hoạt
        DaKichHoat=False,

        # Bắt buộc đổi mật khẩu
        BatBuocDoiMatKhau=True,
        CanDoiMatKhau=True,

        # Mật khẩu tạm thời có hiệu lực 24 giờ
        MatKhauTamThoiHetHan=(
            temporary_password_expiry
        ),

        SoLanDangNhapSai=0,
        KhoaDen=None,
        LyDoKhoa=None,
        TokenValidAfter=None,
        NgayTao=now,
        NgayCapNhat=now,
    )

    try:
        # ====================================================
        # 8. INSERT USER
        # ====================================================

        db.add(user)

        # SQL Server sinh NguoiDungId
        db.flush()

        if not user.NguoiDungId:
            raise HTTPException(
                status_code=500,
                detail="Không lấy được NguoiDungId vừa tạo",
            )

        # ====================================================
        # 9. GÁN VAI TRÒ
        #
        # ĐÂY LÀ PHẦN SỬA QUAN TRỌNG NHẤT
        #
        # Luôn sử dụng selected_role_id.
        # Không sử dụng index của danh sách vai trò.
        # ====================================================

        db.execute(
            text("""
                INSERT INTO NguoiDung_VaiTro
                (
                    NguoiDungId,
                    VaiTroId
                )
                VALUES
                (
                    :nguoi_dung_id,
                    :vai_tro_id
                )
            """),
            {
                "nguoi_dung_id": user.NguoiDungId,
                "vai_tro_id": selected_role_id,
            },
        )

        # ====================================================
        # 10. KIỂM TRA LẠI VAI TRÒ VỪA INSERT
        #
        # Nếu DB lưu sai ID -> rollback ngay.
        # ====================================================

        inserted_role = db.execute(
            text("""
                SELECT TOP 1
                    ndvt.VaiTroId
                FROM NguoiDung_VaiTro ndvt
                WHERE ndvt.NguoiDungId = :nguoi_dung_id
                ORDER BY ndvt.VaiTroId
            """),
            {
                "nguoi_dung_id": user.NguoiDungId,
            },
        ).scalar()

        if inserted_role is None:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Không thể gán vai trò "
                    "cho tài khoản"
                ),
            )

        inserted_role_id = int(inserted_role)

        if inserted_role_id != selected_role_id:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Lỗi gán vai trò: "
                    f"đã chọn VaiTroId={selected_role_id} "
                    f"nhưng DB ghi VaiTroId={inserted_role_id}"
                ),
            )

        # ====================================================
        # 11. TẠO TOKEN KÍCH HOẠT
        # ====================================================

        raw_activation_token = (
            secrets.token_urlsafe(32)
        )

        activation_token = TokenKichHoat(
            NguoiDungId=user.NguoiDungId,
            Token=hashlib.sha256(
                raw_activation_token.encode()
            ).hexdigest(),
            ThoiGianTao=now,
            ThoiGianHetHan=(
                temporary_password_expiry
            ),
            DaSuDung=False,
        )

        db.add(activation_token)

        # ====================================================
        # 12. LINK KÍCH HOẠT
        # ====================================================

        activation_link = (
            "http://localhost:5173/login"
            f"?activate={raw_activation_token}"
        )

        # ====================================================
        # 13. GỬI EMAIL
        # ====================================================

        send_activation_email(
            recipient_email=user.Email,
            ho_ten=user.HoTen,
            temporary_password=temporary_password,
            activation_link=activation_link,
        )

        # ====================================================
        # 14. COMMIT
        # ====================================================

        db.commit()
        db.refresh(user)

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "Không thể tạo tài khoản "
                "hoặc gửi email: "
                f"{exc}"
            ),
        )

    # ========================================================
    # 15. LẤY LẠI VAI TRÒ SAU KHI GÁN
    #
    # Response lấy trực tiếp từ quan hệ DB.
    # ========================================================

    final_role = db.execute(
        text("""
            SELECT TOP 1
                vt.VaiTroId,
                vt.TenVaiTro
            FROM NguoiDung_VaiTro ndvt
            INNER JOIN VaiTro vt
                ON ndvt.VaiTroId = vt.VaiTroId
            WHERE ndvt.NguoiDungId = :nguoi_dung_id
              AND ndvt.VaiTroId = :vai_tro_id
        """),
        {
            "nguoi_dung_id": user.NguoiDungId,
            "vai_tro_id": selected_role_id,
        },
    ).mappings().first()

    if not final_role:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không thể xác nhận vai trò "
                "của tài khoản vừa tạo"
            ),
        )

    return {
        "message": "Tạo tài khoản thành công",
        "nguoiDungId": user.NguoiDungId,
        "hoTen": user.HoTen,
        "email": user.Email,

        # Vai trò lấy trực tiếp từ quan hệ DB
        "vaiTro": {
            "vaiTroId": int(
                final_role["VaiTroId"]
            ),
            "tenVaiTro": final_role["TenVaiTro"],
        },

        "daKichHoat": user.DaKichHoat,
        "batBuocDoiMatKhau": (
            user.BatBuocDoiMatKhau
        ),
        "yeuCauDoiMatKhau": (
            user.CanDoiMatKhau
        ),
        "matKhauTamThoiHetHan": (
            user.MatKhauTamThoiHetHan
        ),
    }


# ============================================================
# ĐĂNG NHẬP
# ============================================================

def login_user(
    db: Session,
    request: LoginRequest,
):
    email = str(request.email).strip().lower()

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng",
        )

    if not getattr(user, "DaKichHoat", True):
        raise HTTPException(
            status_code=403,
            detail="Tài khoản chưa được kích hoạt",
        )

    now = datetime.now()

    # ========================================================
    # KIỂM TRA KHÓA
    # ========================================================

    if user.TrangThai == "BiKhoa":
        reason = (
            f": {user.LyDoKhoa}"
            if user.LyDoKhoa
            else ""
        )

        raise HTTPException(
            status_code=423,
            detail=(
                f"Tài khoản đã bị khóa{reason}"
            ),
        )

    if user.KhoaDen and user.KhoaDen > now:
        raise HTTPException(
            status_code=423,
            detail="Tài khoản đang bị khóa tạm thời",
        )

    if user.KhoaDen and user.KhoaDen <= now:
        user.KhoaDen = None
        user.SoLanDangNhapSai = 0
        user.TrangThai = "HoatDong"
        user.LyDoKhoa = None

    # ========================================================
    # KIỂM TRA PASSWORD
    # ========================================================

    try:
        password_correct = password_hash.verify(
            request.password,
            user.MatKhauHash,
        )
    except Exception:
        password_correct = False

    if not password_correct:
        user.SoLanDangNhapSai = (
            user.SoLanDangNhapSai or 0
        ) + 1

        if user.SoLanDangNhapSai >= 5:
            user.KhoaDen = (
                now + timedelta(minutes=15)
            )

            user.LyDoKhoa = (
                "Sai mật khẩu 5 lần liên tiếp"
            )

            db.commit()

            raise HTTPException(
                status_code=423,
                detail=(
                    "Tài khoản đã bị khóa tạm thời "
                    "15 phút do nhập sai mật khẩu "
                    "5 lần liên tiếp"
                ),
            )

        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng",
        )

    # ========================================================
    # KIỂM TRA MẬT KHẨU TẠM THỜI
    # ========================================================

    if (
        user.CanDoiMatKhau
        and user.MatKhauTamThoiHetHan
        and user.MatKhauTamThoiHetHan <= now
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Mật khẩu tạm thời đã hết hạn. "
                "Vui lòng liên hệ quản trị viên "
                "để được cấp lại."
            ),
        )

    user.SoLanDangNhapSai = 0
    user.KhoaDen = None
    user.LyDoKhoa = None
    user.TrangThai = "HoatDong"
    user.NgayCapNhat = now

    db.commit()
    db.refresh(user)

    user_id = user.NguoiDungId

    # ========================================================
    # LẤY VAI TRÒ
    # ========================================================

    roles = db.execute(
        text("""
            SELECT
                vt.VaiTroId,
                vt.TenVaiTro
            FROM NguoiDung_VaiTro ndvt
            INNER JOIN VaiTro vt
                ON ndvt.VaiTroId = vt.VaiTroId
            WHERE ndvt.NguoiDungId = :nguoi_dung_id
            ORDER BY vt.VaiTroId
        """),
        {
            "nguoi_dung_id": user_id,
        },
    ).mappings().all()

    # ========================================================
    # LẤY QUYỀN
    # ========================================================

    permissions = db.execute(
        text("""
            SELECT DISTINCT
                q.QuyenId,
                q.MaQuyen,
                q.TenQuyen
            FROM NguoiDung_VaiTro ndvt

            INNER JOIN VaiTro_Quyen vtq
                ON ndvt.VaiTroId = vtq.VaiTroId
            INNER JOIN Quyen q
                ON vtq.QuyenId = q.QuyenId

            WHERE ndvt.NguoiDungId = :nguoi_dung_id
            ORDER BY q.QuyenId
        """),
        {
            "nguoi_dung_id": user_id,
        },
    ).mappings().all()

    return {
        "message": "Đăng nhập thành công",

        "access_token": create_access_token({
            "sub": user.Email,
            "user_id": user_id,
            "roles": [
                role["TenVaiTro"]
                for role in roles
            ],
            "yeuCauDoiMatKhau": bool(
                user.CanDoiMatKhau
            ),
        }),

        "token_type": "bearer",

        "nguoiDungId": user.NguoiDungId,
        "hoTen": user.HoTen,
        "email": user.Email,

        "yeuCauDoiMatKhau": bool(
            user.CanDoiMatKhau
        ),

        "vaiTro": [
            {
                "vaiTroId": role["VaiTroId"],
                "tenVaiTro": role["TenVaiTro"],
            }
            for role in roles
        ],

        "quyen": [
            {
                "quyenId": permission["QuyenId"],
                "maQuyen": permission["MaQuyen"],
                "tenQuyen": permission["TenQuyen"],
            }
            for permission in permissions
        ],
    }


# ============================================================
# ĐĂNG XUẤT
# ============================================================

def logout_user(
    db: Session,
    token: str,
):
    try:
        payload = decode_access_token(token)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token hết hạn",
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Token không hợp lệ",
        )

    jti = payload.get("jti")
    exp = payload.get("exp")

    if not jti or not exp:
        raise HTTPException(
            status_code=401,
            detail="Token không hợp lệ",
        )

    exists = (
        db.query(RevokedToken)
        .filter(RevokedToken.Jti == jti)
        .first()
    )

    if exists:
        return {
            "message": "Đăng xuất thành công"
        }

    revoked = RevokedToken(
        Jti=jti,
        ExpiresAt=datetime.fromtimestamp(
            exp,
            tz=timezone.utc,
        ).replace(tzinfo=None),
    )

    try:
        db.add(revoked)
        db.commit()

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể đăng xuất",
        )

    return {
        "message": "Đăng xuất thành công"
    }


# ============================================================
# ĐỔI MẬT KHẨU
# ============================================================

def update_password(
    db: Session,
    user: NguoiDung,
    current_password: str,
    new_password: str,
):
    try:
        correct = password_hash.verify(
            current_password,
            user.MatKhauHash,
        )
    except Exception:
        correct = False

    if not correct:
        raise HTTPException(
            status_code=400,
            detail="Mật khẩu hiện tại không đúng",
        )

    now = datetime.now()

    user.MatKhauHash = password_hash.hash(
        new_password
    )

    user.NgayCapNhat = now
    user.TokenValidAfter = utc_now()

    user.BatBuocDoiMatKhau = False
    user.CanDoiMatKhau = False
    user.MatKhauTamThoiHetHan = None

    try:
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể cập nhật mật khẩu",
        )

    return {
        "message": "Cập nhật mật khẩu thành công"
    }


# ============================================================
# QUÊN MẬT KHẨU
# ============================================================

def forgot_password(
    db: Session,
    request: ForgotPasswordRequest,
):
    email = str(request.email).strip().lower()

    message = (
        "Nếu email tồn tại trong hệ thống, "
        "hướng dẫn đặt lại mật khẩu đã được gửi."
    )

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    if not user:
        return {
            "message": message
        }

    raw_token = secrets.token_urlsafe(32)

    now = datetime.now()

    reset_token = TokenMatKhau(
        NguoiDungId=user.NguoiDungId,
        Token=hashlib.sha256(
            raw_token.encode()
        ).hexdigest(),
        ThoiGianTao=now,
        ThoiGianHetHan=(
            now + timedelta(minutes=30)
        ),
        DaSuDung=False,
    )

    try:
        db.add(reset_token)
        db.commit()

    except Exception as exc:
        db.rollback()

        logger.exception(
            "Failed to save password-reset token for user_id=%s",
            user.NguoiDungId,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Không thể tạo yêu cầu đặt lại mật khẩu lúc này. "
                "Vui lòng thử lại sau."
            ),
        ) from exc

    reset_link = (
        f"{FRONTEND_URL.rstrip('/')}/reset-password"
        f"?token={raw_token}"
    )

    try:
        send_reset_password_email(
            recipient_email=user.Email,
            reset_link=reset_link,
        )

    except RuntimeError as exc:
        logger.exception(
            "Failed to send password-reset email for user_id=%s",
            user.NguoiDungId,
        )

        try:
            db.delete(reset_token)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "Failed to remove undelivered password-reset token "
                "for user_id=%s",
                user.NguoiDungId,
            )

        raise HTTPException(
            status_code=503,
            detail=(
                "Không thể gửi email đặt lại mật khẩu lúc này. "
                "Vui lòng thử lại sau."
            ),
        ) from exc

    return {
        "message": message
    }


# ============================================================
# KÍCH HOẠT TÀI KHOẢN
# ============================================================

def activate_account(
    db: Session,
    token: str,
):
    token_hash = hashlib.sha256(
        token.encode()
    ).hexdigest()

    activation_token = (
        db.query(TokenKichHoat)
        .filter(
            TokenKichHoat.Token == token_hash,
            TokenKichHoat.DaSuDung == False,
        )
        .first()
    )

    if not activation_token:
        raise HTTPException(
            status_code=400,
            detail="Token kích hoạt không hợp lệ",
        )

    now = datetime.now()

    if activation_token.ThoiGianHetHan < now:
        activation_token.DaSuDung = True
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Token kích hoạt đã hết hạn",
        )

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId
            == activation_token.NguoiDungId
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng",
        )

    user.DaKichHoat = True
    user.NgayCapNhat = now

    activation_token.DaSuDung = True

    try:
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể kích hoạt tài khoản",
        )

    return {
        "message": "Kích hoạt tài khoản thành công",
        "nguoiDungId": user.NguoiDungId,
        "email": user.Email,
        "daKichHoat": user.DaKichHoat,
    }


# ============================================================
# KIỂM TRA RESET TOKEN
# ============================================================

def validate_reset_token(
    db: Session,
    token: str,
):
    token_hash = hashlib.sha256(
        token.encode()
    ).hexdigest()

    reset_token = (
        db.query(TokenMatKhau)
        .filter(
            TokenMatKhau.Token == token_hash,
            TokenMatKhau.DaSuDung == False,
        )
        .first()
    )

    if not reset_token:
        raise HTTPException(
            status_code=400,
            detail="Token không hợp lệ",
        )

    now = datetime.now()

    if reset_token.ThoiGianHetHan < now:
        reset_token.DaSuDung = True
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Token đã hết hạn",
        )

    return {
        "message": "Token hợp lệ"
    }


# ============================================================
# RESET PASSWORD
# ============================================================

def reset_password(
    db: Session,
    request: ResetPasswordRequest,
):
    token_hash = hashlib.sha256(
        request.token.encode()
    ).hexdigest()

    reset_token = (
        db.query(TokenMatKhau)
        .filter(
            TokenMatKhau.Token == token_hash,
            TokenMatKhau.DaSuDung == False,
        )
        .first()
    )

    if not reset_token:
        raise HTTPException(
            status_code=400,
            detail="Token không hợp lệ",
        )

    now = datetime.now()

    if reset_token.ThoiGianHetHan < now:
        reset_token.DaSuDung = True
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Token đã hết hạn",
        )

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId
            == reset_token.NguoiDungId
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng",
        )

    user.MatKhauHash = password_hash.hash(
        request.new_password
    )

    user.TokenValidAfter = utc_now()
    user.NgayCapNhat = now

    user.BatBuocDoiMatKhau = False
    user.CanDoiMatKhau = False
    user.MatKhauTamThoiHetHan = None

    reset_token.DaSuDung = True

    try:
        db.commit()

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể đặt lại mật khẩu",
        )

    return {
        "message": "Đặt lại mật khẩu thành công"
    }


# ============================================================
# CẬP NHẬT USER
# ============================================================

def update_user(
    db: Session,
    user_id: int,
    request,
):
    user = _find_user(db, user_id)

    if request.email:
        email = str(request.email).strip().lower()

        exists = (
            db.query(NguoiDung)
            .filter(
                NguoiDung.Email == email,
                NguoiDung.NguoiDungId != user_id,
            )
            .first()
        )

        if exists:
            raise HTTPException(
                status_code=400,
                detail="Email đã tồn tại",
            )

        user.Email = email

    if request.ho_ten:
        user.HoTen = request.ho_ten.strip()

    if request.so_dien_thoai:
        user.SoDienThoai = (
            request.so_dien_thoai.strip()
        )

    user.NgayCapNhat = datetime.now()

    try:
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể cập nhật",
        )

    return {
        "message": "Cập nhật thành công"
    }


# ============================================================
# XÓA NGƯỜI DÙNG
# ============================================================

def delete_user(
    db: Session,
    user_id: int,
):
    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId == user_id
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng",
        )

    email = user.Email
    ho_ten = user.HoTen

    try:
        # Xóa quan hệ người dùng - vai trò
        db.execute(
            text("""
                DELETE FROM NguoiDung_VaiTro
                WHERE NguoiDungId = :nguoi_dung_id
            """),
            {
                "nguoi_dung_id": user_id
            },
        )

        # Xóa token kích hoạt
        db.execute(
            text("""
                DELETE FROM TokenKichHoat
                WHERE NguoiDungId = :nguoi_dung_id
            """),
            {
                "nguoi_dung_id": user_id
            },
        )

        # Xóa token đặt lại mật khẩu
        db.execute(
            text("""
                DELETE FROM TokenMatKhau
                WHERE NguoiDungId = :nguoi_dung_id
            """),
            {
                "nguoi_dung_id": user_id
            },
        )

        # Xóa tài khoản
        db.delete(user)

        db.commit()

    except Exception as exc:
        db.rollback()

        print(
            f"[DELETE USER] Lỗi xóa tài khoản "
            f"{user_id}: {exc}"
        )

        raise HTTPException(
            status_code=500,
            detail="Không thể xóa tài khoản",
        )

    return {
        "message": "Xóa tài khoản thành công",
        "nguoiDungId": user_id,
        "hoTen": ho_ten,
        "email": email,
    }


# ============================================================
# KHÓA USER
# ============================================================

def lock_user(
    db: Session,
    user_id: int,
    request: NguoiDungLock,
):
    user = _find_user(db, user_id)

    user.TrangThai = "BiKhoa"
    user.KhoaDen = None

    user.LyDoKhoa = request.ly_do_khoa.strip()

    now = datetime.now()
    user.TokenValidAfter = utc_now()
    user.NgayCapNhat = now

    try:
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể khóa tài khoản",
        )

    return {
        "message": "Khóa tài khoản thành công",
        "nguoiDungId": user.NguoiDungId,
        "trangThai": user.TrangThai,
        "lyDoKhoa": user.LyDoKhoa,
    }


# ============================================================
# MỞ KHÓA USER
# ============================================================

def unlock_user(
    db: Session,
    user_id: int,
):
    user = _find_user(db, user_id)

    if user.TrangThai != "BiKhoa":
        raise HTTPException(
            status_code=400,
            detail="Tài khoản chưa bị khóa",
        )

    user.TrangThai = "HoatDong"
    user.KhoaDen = None
    user.LyDoKhoa = None
    user.SoLanDangNhapSai = 0
    now = datetime.now()
    user.TokenValidAfter = utc_now()
    user.NgayCapNhat = now

    try:
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể mở khóa tài khoản",
        )

    return {
        "message": "Mở khóa tài khoản thành công",
        "user": {
            **_user_data(user),
            "ngayCapNhat": user.NgayCapNhat,
        },
    }