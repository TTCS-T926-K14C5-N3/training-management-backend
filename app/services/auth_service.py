from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from app.models.nguoi_dung import NguoiDung
from app.models.revoked_token import RevokedToken
from app.models.token_mat_khau import TokenMatKhau

from app.schemas.login import LoginRequest
from app.schemas.register import RegisterRequest
from app.schemas.forgot_password import ForgotPasswordRequest
from app.schemas.reset_password import ResetPasswordRequest

from app.services.email_service import send_reset_password_email

from app.core.security import (
    create_access_token,
    decode_access_token
)

from datetime import datetime, timedelta, timezone

import hashlib
import secrets
import jwt


# ============================================================
# PASSWORD HASH
# ============================================================

password_hash = PasswordHash.recommended()


# ============================================================
# ĐĂNG KÝ
# ============================================================

def register_user(
    db: Session,
    request: RegisterRequest
):
    # Chuẩn hóa dữ liệu
    email = str(request.email).strip().lower()
    ho_ten = request.ho_ten.strip()

    so_dien_thoai = (
        request.so_dien_thoai.strip()
        if request.so_dien_thoai
        else None
    )

    # --------------------------------------------------------
    # Kiểm tra email đã tồn tại
    # --------------------------------------------------------

    existing_user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email đã được sử dụng"
        )

    # --------------------------------------------------------
    # Hash mật khẩu
    # --------------------------------------------------------

    hashed_password = password_hash.hash(
        request.password
    )

    now = datetime.now()

    # --------------------------------------------------------
    # Tạo người dùng
    # --------------------------------------------------------

    new_user = NguoiDung(
        HoTen=ho_ten,
        Email=email,
        SoDienThoai=so_dien_thoai,
        MatKhauHash=hashed_password,
        TrangThai="HoatDong",
        SoLanDangNhapSai=0,
        KhoaDen=None,
        LyDoKhoa=None,
        NgayTao=now,
        NgayCapNhat=now
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể tạo tài khoản"
        )

    return {
        "message": "Đăng ký thành công",
        "user": {
            "nguoiDungId": new_user.NguoiDungId,
            "hoTen": new_user.HoTen,
            "email": new_user.Email,
            "soDienThoai": new_user.SoDienThoai,
            "trangThai": new_user.TrangThai
        }
    }


# ============================================================
# ĐĂNG NHẬP
# ============================================================

def login_user(
    db: Session,
    request: LoginRequest
):
    email = str(request.email).strip().lower()

    # --------------------------------------------------------
    # Tìm người dùng theo email
    # --------------------------------------------------------

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    # Không tiết lộ email có tồn tại hay không
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng"
        )

    now = datetime.now()

    # --------------------------------------------------------
    # Kiểm tra tài khoản đang bị khóa
    # --------------------------------------------------------

    if user.KhoaDen and user.KhoaDen > now:
        raise HTTPException(
            status_code=423,
            detail="Tài khoản đang bị khóa, vui lòng thử lại sau"
        )

    # --------------------------------------------------------
    # Nếu hết thời gian khóa -> mở khóa
    # --------------------------------------------------------

    if user.KhoaDen and user.KhoaDen <= now:
        user.KhoaDen = None
        user.SoLanDangNhapSai = 0
        user.TrangThai = "HoatDong"
        user.LyDoKhoa = None
        user.NgayCapNhat = now

    db.commit()
    db.refresh(user)

    # --------------------------------------------------------
    # Kiểm tra mật khẩu
    # --------------------------------------------------------

    try:
        password_correct = password_hash.verify(
            request.password,
            user.MatKhauHash
        )

    except Exception:
        password_correct = False

    # --------------------------------------------------------
    # Mật khẩu sai
    # --------------------------------------------------------

    if not password_correct:

        if user.SoLanDangNhapSai is None:
            user.SoLanDangNhapSai = 0

        user.SoLanDangNhapSai += 1
        user.NgayCapNhat = now

        # Sai 5 lần -> khóa 15 phút
        if user.SoLanDangNhapSai >= 5:
            user.KhoaDen = (
                now + timedelta(minutes=15)
            )

            user.TrangThai = "BiKhoa"

            user.LyDoKhoa = (
                "Sai mật khẩu 5 lần liên tiếp"
            )

        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng"
        )

    # --------------------------------------------------------
    # Đăng nhập thành công
    # --------------------------------------------------------

    user.SoLanDangNhapSai = 0
    user.KhoaDen = None
    user.TrangThai = "HoatDong"
    user.LyDoKhoa = None
    user.NgayCapNhat = now

    # --------------------------------------------------------
    # Lấy vai trò của người dùng
    # --------------------------------------------------------

    role_query = text("""
        SELECT
            vt.VaiTroId,
            vt.TenVaiTro
        FROM VaiTro vt

        INNER JOIN NguoiDung_VaiTro ndvt
            ON vt.VaiTroId = ndvt.VaiTroId

        WHERE ndvt.NguoiDungId = :nguoi_dung_id
    """)

    roles = db.execute(
        role_query,
        {
            "nguoi_dung_id": user.NguoiDungId
        }
    ).mappings().all()

    db.commit()
    db.refresh(user)

    # --------------------------------------------------------
    # Tạo JWT Access Token
    # --------------------------------------------------------

    token_payload = {
        "sub": user.Email,
        "user_id": user.NguoiDungId
    }

    access_token = create_access_token(
        data=token_payload
    )

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "message": "Đăng nhập thành công",

        "access_token": access_token,
        "token_type": "bearer",

        "nguoiDungId": user.NguoiDungId,
        "hoTen": user.HoTen,
        "email": user.Email,

        "vaiTro": [
            {
                "vaiTroId": role["VaiTroId"],
                "tenVaiTro": role["TenVaiTro"]
            }
            for role in roles
        ]
    }


# ============================================================
# ĐĂNG XUẤT
# ============================================================

def logout_user(
    db: Session,
    token: str
):
    try:
        payload = decode_access_token(token)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Phiên đăng nhập đã hết hạn"
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Token không hợp lệ"
        )

    jti = payload.get("jti")
    exp = payload.get("exp")

    if not jti or not exp:
        raise HTTPException(
            status_code=401,
            detail="Token không hợp lệ"
        )

    # Kiểm tra token đã bị revoke trước đó chưa
    existing_token = (
        db.query(RevokedToken)
        .filter(RevokedToken.Jti == jti)
        .first()
    )

    if existing_token:
        return {
            "message": "Đăng xuất thành công"
        }

    expires_at = datetime.fromtimestamp(
        exp,
        tz=timezone.utc
    ).replace(tzinfo=None)

    revoked_token = RevokedToken(
        Jti=jti,
        ExpiresAt=expires_at
    )

    try:
        db.add(revoked_token)
        db.commit()

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể đăng xuất"
        )

    return {
        "message": "Đăng xuất thành công"
    }




# ============================================================

# CẬP NHẬT MẬT KHẨU
# ============================================================

def update_password(
    db: Session,
    user: NguoiDung,
    current_password: str,
    new_password: str
):
    # Kiểm tra mật khẩu hiện tại
    try:
        password_correct = password_hash.verify(
            current_password,
            user.MatKhauHash
        )
    except Exception:
        password_correct = False

    if not password_correct:
        raise HTTPException(
            status_code=400,
            detail="Mật khẩu hiện tại không đúng"
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
   
    # Hash mật khẩu mới
    new_password_hash = password_hash.hash(
        new_password
    )

    # Cập nhật mật khẩu
    user.MatKhauHash = new_password_hash
    user.NgayCapNhat = now

    # Thu hồi các token được cấp trước thời điểm đổi mật khẩu
    user.TokenValidAfter = now

    try:
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể cập nhật mật khẩu"
        )

    return {
        "message": "Cập nhật mật khẩu thành công"
    }


# ============================================================
# QUÊN MẬT KHẨU
# ============================================================

def forgot_password(
    db: Session,
    request: ForgotPasswordRequest
):
    """
    Tạo token đặt lại mật khẩu và gửi email.

    Token thật không được lưu trực tiếp trong database.
    Database chỉ lưu SHA-256 hash của token.
    """

    email = str(request.email).strip().lower()

    # --------------------------------------------------------
    # Message dùng chung
    # --------------------------------------------------------

    generic_message = (
        "Nếu email tồn tại trong hệ thống, "
        "hướng dẫn đặt lại mật khẩu đã được gửi đến email."
    )

    # --------------------------------------------------------
    # Tìm người dùng
    # --------------------------------------------------------

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    # Không tiết lộ email có tồn tại hay không
    if not user:
        return {
            "message": generic_message
        }

    # --------------------------------------------------------
    # Tạo token ngẫu nhiên
    # --------------------------------------------------------

    raw_token = secrets.token_urlsafe(32)

    # Hash token trước khi lưu DB
    token_hash = hashlib.sha256(
        raw_token.encode("utf-8")
    ).hexdigest()

    now = datetime.now()

    expires_at = (
        now + timedelta(minutes=30)
    )

    # --------------------------------------------------------
    # Hủy các token reset cũ chưa sử dụng
    # --------------------------------------------------------

    old_tokens = (
        db.query(TokenMatKhau)
        .filter(
            TokenMatKhau.NguoiDungId == user.NguoiDungId,
            TokenMatKhau.DaSuDung == False
        )
        .all()
    )

    for old_token in old_tokens:
        old_token.DaSuDung = True

    # --------------------------------------------------------
    # Tạo token mới
    # --------------------------------------------------------

    reset_token = TokenMatKhau(
        NguoiDungId=user.NguoiDungId,
        Token=token_hash,
        ThoiGianTao=now,
        ThoiGianHetHan=expires_at,
        DaSuDung=False
    )

    try:
        db.add(reset_token)
        db.commit()

    except Exception as exc:
        db.rollback()

        print(
            f"[FORGOT PASSWORD] Lỗi lưu TokenMatKhau: {exc}"
        )

        return {
            "message": generic_message
        }
    # --------------------------------------------------------
    # Tạo link reset
    # --------------------------------------------------------

    reset_link = (
        "http://localhost:5173/reset-password"
        f"?token={raw_token}"
    )

    # --------------------------------------------------------
    # Gửi email
    # --------------------------------------------------------

    try:
        send_reset_password_email(
            recipient_email=user.Email,
            reset_link=reset_link
        )

    except Exception:
        # Không trả lỗi chi tiết SMTP ra ngoài.
        #
        # Trong môi trường thực tế nên ghi log để
        # quản trị viên kiểm tra.
        return {
            "message": generic_message
        }

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "message": generic_message
    }


# ============================================================
# ĐẶT LẠI MẬT KHẨU
# ============================================================

def reset_password(
    db: Session,
    request: ResetPasswordRequest
):
    """
    Đặt lại mật khẩu bằng reset token.

    Điều kiện:
    - Token tồn tại
    - Token chưa được sử dụng
    - Token chưa hết hạn
    - Mật khẩu đã được validate bởi Pydantic
    """

    # --------------------------------------------------------
    # Hash token nhận từ client
    # --------------------------------------------------------

    token_hash = hashlib.sha256(
        request.token.encode("utf-8")
    ).hexdigest()

    # --------------------------------------------------------
    # Tìm token
    # --------------------------------------------------------

    reset_token = (
        db.query(TokenMatKhau)
        .filter(
            TokenMatKhau.Token == token_hash,
            TokenMatKhau.DaSuDung == False
        )
        .first()
    )

    # Token không tồn tại hoặc đã sử dụng
    if not reset_token:
        raise HTTPException(
            status_code=400,
            detail="Liên kết đặt lại mật khẩu không hợp lệ"
        )

    now = datetime.now()

    # --------------------------------------------------------
    # Kiểm tra hết hạn
    # --------------------------------------------------------

    if reset_token.ThoiGianHetHan <= now:

        # Đánh dấu token hết hạn là đã sử dụng
        reset_token.DaSuDung = True

        try:
            db.commit()
        except Exception:
            db.rollback()

        raise HTTPException(
            status_code=400,
            detail="Liên kết đặt lại mật khẩu đã hết hạn"
        )

    # --------------------------------------------------------
    # Tìm người dùng
    # --------------------------------------------------------

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
            status_code=400,
            detail="Liên kết đặt lại mật khẩu không hợp lệ"
        )

    # --------------------------------------------------------
    # Hash mật khẩu mới
    # --------------------------------------------------------

    new_password_hash = password_hash.hash(
        request.new_password
    )

    # --------------------------------------------------------
    # Cập nhật mật khẩu
    # --------------------------------------------------------

    user.MatKhauHash = new_password_hash
    user.NgayCapNhat = now

    # Thu hồi các JWT được cấp trước khi reset
    user.TokenValidAfter = now

    # --------------------------------------------------------
    # Token reset chỉ được dùng một lần
    # --------------------------------------------------------

    reset_token.DaSuDung = True

    # --------------------------------------------------------
    # Lưu tất cả thay đổi
    # --------------------------------------------------------

    try:
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể đặt lại mật khẩu"
        )

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "message": "Đặt lại mật khẩu thành công"
    }