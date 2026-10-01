from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from app.schemas.nguoi_dung import (
    NguoiDungCreate,
    NguoiDungLock,
)

from app.models.nguoi_dung import NguoiDung
from app.models.revoked_token import RevokedToken
from app.models.token_mat_khau import TokenMatKhau

from app.schemas.login import LoginRequest
from app.schemas.register import RegisterRequest
from app.schemas.forgot_password import ForgotPasswordRequest
from app.schemas.reset_password import ResetPasswordRequest

from app.services.email_service import (
    send_reset_password_email
)

from app.core.security import (
    create_access_token,
    decode_access_token
)

from datetime import (
    datetime,
    timedelta,
    timezone,
)

import hashlib
import secrets
import jwt


# ============================================================
# PASSWORD HASH
# ============================================================

password_hash = PasswordHash.recommended()


# ============================================================
# HELPER - THỜI GIAN UTC CHO SQL SERVER
# ============================================================

def utc_now():
    """
    Lấy thời gian UTC hiện tại.

    SQL Server DATETIME/DATETIME2 không lưu timezone,
    nên lưu UTC dạng naive datetime.
    """

    return datetime.now(timezone.utc).replace(
        tzinfo=None
    )


# ============================================================
# ĐĂNG KÝ USER
# ============================================================

def register_user(
    db: Session,
    request: RegisterRequest
):

    email = str(
        request.email
    ).strip().lower()

    ho_ten = request.ho_ten.strip()

    so_dien_thoai = (
        request.so_dien_thoai.strip()
        if request.so_dien_thoai
        else None
    )

    existing_user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.Email == email
        )
        .first()
    )

    if existing_user:

        raise HTTPException(
            status_code=400,
            detail="Email đã được sử dụng"
        )

    now = utc_now()

    new_user = NguoiDung(

        HoTen=ho_ten,

        Email=email,

        SoDienThoai=so_dien_thoai,

        MatKhauHash=password_hash.hash(
            request.password
        ),

        TrangThai="HoatDong",

        SoLanDangNhapSai=0,

        KhoaDen=None,

        LyDoKhoa=None,

        NgayTao=now,

        NgayCapNhat=now,

        TokenValidAfter=None,
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

        "message":
            "Đăng ký thành công",

        "user": {

            "nguoiDungId":
                new_user.NguoiDungId,

            "hoTen":
                new_user.HoTen,

            "email":
                new_user.Email,

            "trangThai":
                new_user.TrangThai

        }

    }


# ============================================================
# ADMIN TẠO USER
# ============================================================

def create_user(
    db: Session,
    request: NguoiDungCreate
):

    email = str(
        request.email
    ).strip().lower()

    exists = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.Email == email
        )
        .first()
    )

    if exists:

        raise HTTPException(
            status_code=400,
            detail="Email đã được sử dụng"
        )

    now = utc_now()

    user = NguoiDung(

        HoTen=request.ho_ten.strip(),

        Email=email,

        SoDienThoai=request.so_dien_thoai,

        MatKhauHash=password_hash.hash(
            request.password
        ),

        TrangThai="HoatDong",

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
            detail="Không thể tạo người dùng"
        )

    return {

        "message":
            "Tạo người dùng thành công",

        "user": {

            "nguoiDungId":
                user.NguoiDungId,

            "hoTen":
                user.HoTen,

            "email":
                user.Email,

            "trangThai":
                user.TrangThai

        }

    }


# ============================================================
# ĐĂNG NHẬP
# ============================================================

def login_user(
    db: Session,
    request: LoginRequest
):

    # ========================================================
    # CHUẨN HÓA EMAIL
    # ========================================================

    email = str(
        request.email
    ).strip().lower()

    # ========================================================
    # TÌM USER
    # ========================================================

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.Email == email
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng"
        )

    # ========================================================
    # THỜI GIAN UTC
    # ========================================================

    now = utc_now()

    # ========================================================
    # KIỂM TRA TÀI KHOẢN BỊ ADMIN KHÓA
    # ========================================================

    if user.TrangThai == "BiKhoa":

        raise HTTPException(
            status_code=423,
            detail=(
                "Tài khoản đã bị khóa"
                +
                (
                    f": {user.LyDoKhoa}"
                    if user.LyDoKhoa
                    else ""
                )
            )
        )

    # ========================================================
    # KIỂM TRA KHÓA TẠM THỜI
    # ========================================================

    if (
        user.KhoaDen
        and user.KhoaDen > now
    ):

        raise HTTPException(
            status_code=423,
            detail="Tài khoản đang bị khóa tạm thời"
        )

    # ========================================================
    # KHÓA TẠM THỜI ĐÃ HẾT HẠN
    # ========================================================

    if (
        user.KhoaDen
        and user.KhoaDen <= now
    ):

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
            user.MatKhauHash
        )

    except Exception:

        password_correct = False

    # ========================================================
    # PASSWORD SAI
    # ========================================================

    if not password_correct:

        if user.SoLanDangNhapSai is None:

            user.SoLanDangNhapSai = 0

        user.SoLanDangNhapSai += 1

        # ----------------------------------------------------
        # SAI 5 LẦN → KHÓA TẠM THỜI 15 PHÚT
        # ----------------------------------------------------

        if user.SoLanDangNhapSai >= 5:

            user.KhoaDen = (
                now + timedelta(minutes=15)
            )

            user.TrangThai = "KhoaTamThoi"

            user.LyDoKhoa = (
                "Sai mật khẩu 5 lần liên tiếp"
            )

            db.commit()

            # Trả đúng 423 ngay tại lần sai thứ 5
            raise HTTPException(
                status_code=423,
                detail=(
                    "Tài khoản đã bị khóa tạm thời "
                    "15 phút do nhập sai mật khẩu "
                    "5 lần liên tiếp"
                )
            )

        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng"
        )

    # ========================================================
    # LOGIN THÀNH CÔNG
    # ========================================================

    user.SoLanDangNhapSai = 0

    user.KhoaDen = None

    user.LyDoKhoa = None

    user.TrangThai = "HoatDong"

    user.NgayCapNhat = now

    db.commit()

    db.refresh(user)

    # ========================================================
    # LẤY VAI TRÒ
    # ========================================================

    role_query = text("""
        SELECT
            vt.VaiTroId,
            vt.TenVaiTro
        FROM NguoiDung_VaiTro ndvt
        INNER JOIN VaiTro vt
            ON ndvt.VaiTroId = vt.VaiTroId
        WHERE ndvt.NguoiDungId = :nguoi_dung_id
        ORDER BY vt.VaiTroId
    """)

    role_result = db.execute(
        role_query,
        {
            "nguoi_dung_id": user.NguoiDungId
        }
    ).mappings().all()

    vai_tro = [
        {
            "vaiTroId": role["VaiTroId"],
            "tenVaiTro": role["TenVaiTro"]
        }
        for role in role_result
    ]

    # ========================================================
    # LẤY QUYỀN
    # ========================================================

    permission_query = text("""
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
    """)

    permission_result = db.execute(
        permission_query,
        {
            "nguoi_dung_id": user.NguoiDungId
        }
    ).mappings().all()

    quyen = [
        {
            "quyenId": permission["QuyenId"],
            "maQuyen": permission["MaQuyen"],
            "tenQuyen": permission["TenQuyen"]
        }
        for permission in permission_result
    ]

    # ========================================================
    # TẠO JWT
    # ========================================================

    token = create_access_token(
        {
            "sub": user.Email,
            "user_id": user.NguoiDungId
        }
    )

    # ========================================================
    # RESPONSE LOGIN
    # ========================================================

    return {

        "message":
            "Đăng nhập thành công",

        "access_token":
            token,

        "token_type":
            "bearer",

        "nguoiDungId":
            user.NguoiDungId,

        "hoTen":
            user.HoTen,

        "email":
            user.Email,

        "vaiTro":
            vai_tro,

        "quyen":
            quyen

    }


# ============================================================
# ĐĂNG XUẤT
# ============================================================

def logout_user(
    db: Session,
    token: str
):

    try:

        payload = decode_access_token(
            token
        )

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

    exists = (
        db.query(RevokedToken)
        .filter(
            RevokedToken.Jti == jti
        )
        .first()
    )

    if exists:

        return {
            "message":
                "Đăng xuất thành công"
        }

    revoked = RevokedToken(

        Jti=jti,

        ExpiresAt=datetime.fromtimestamp(
            exp,
            tz=timezone.utc
        ).replace(
            tzinfo=None
        )

    )

    try:

        db.add(revoked)

        db.commit()

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể đăng xuất"
        )

    return {

        "message":
            "Đăng xuất thành công"

    }


# ============================================================
# ĐỔI MẬT KHẨU
# ============================================================

def update_password(
    db: Session,
    user: NguoiDung,
    current_password: str,
    new_password: str
):

    try:

        correct = password_hash.verify(
            current_password,
            user.MatKhauHash
        )

    except Exception:

        correct = False

    if not correct:

        raise HTTPException(
            status_code=400,
            detail="Mật khẩu hiện tại không đúng"
        )

    now = utc_now()

    user.MatKhauHash = password_hash.hash(
        new_password
    )

    user.NgayCapNhat = now

    # ========================================================
    # THU HỒI JWT CŨ
    # ========================================================

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

        "message":
            "Cập nhật mật khẩu thành công"

    }


# ============================================================
# QUÊN MẬT KHẨU
# ============================================================

def forgot_password(
    db: Session,
    request: ForgotPasswordRequest
):

    email = str(
        request.email
    ).strip().lower()

    message = (
        "Nếu email tồn tại trong hệ thống, "
        "hướng dẫn đặt lại mật khẩu đã được gửi."
    )

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.Email == email
        )
        .first()
    )

    if not user:

        return {
            "message":
                message
        }

    raw_token = secrets.token_urlsafe(32)

    token_hash = hashlib.sha256(
        raw_token.encode()
    ).hexdigest()

    now = utc_now()

    reset_token = TokenMatKhau(

        NguoiDungId=user.NguoiDungId,

        Token=token_hash,

        ThoiGianTao=now,

        ThoiGianHetHan=(
            now + timedelta(minutes=30)
        ),

        DaSuDung=False

    )

    try:

        db.add(reset_token)

        db.commit()

    except Exception:

        db.rollback()

        return {
            "message":
                message
        }

    reset_link = (
        "http://localhost:5173/reset-password"
        f"?token={raw_token}"
    )

    try:

        send_reset_password_email(
            recipient_email=user.Email,
            reset_link=reset_link
        )

    except Exception:

        pass

    return {

        "message":
            message

    }


# ============================================================
# RESET PASSWORD
# ============================================================

def reset_password(
    db: Session,
    request: ResetPasswordRequest
):

    token_hash = hashlib.sha256(
        request.token.encode()
    ).hexdigest()

    reset_token = (
        db.query(TokenMatKhau)
        .filter(
            TokenMatKhau.Token == token_hash,
            TokenMatKhau.DaSuDung == False
        )
        .first()
    )

    if not reset_token:

        raise HTTPException(
            status_code=400,
            detail="Token không hợp lệ"
        )

    now = utc_now()

    if reset_token.ThoiGianHetHan < now:

        reset_token.DaSuDung = True

        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Token đã hết hạn"
        )

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId
            ==
            reset_token.NguoiDungId
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng"
        )

    user.MatKhauHash = password_hash.hash(
        request.new_password
    )

    # ========================================================
    # THU HỒI JWT CŨ
    # ========================================================

    user.TokenValidAfter = now

    user.NgayCapNhat = now

    reset_token.DaSuDung = True

    try:

        db.commit()

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể đặt lại mật khẩu"
        )

    return {

        "message":
            "Đặt lại mật khẩu thành công"

    }


# ============================================================
# CẬP NHẬT USER
# ============================================================

def update_user(
    db: Session,
    user_id: int,
    request
):

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId
            ==
            user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng"
        )

    if request.email:

        email = str(
            request.email
        ).strip().lower()

        exists = (
            db.query(NguoiDung)
            .filter(
                NguoiDung.Email == email,
                NguoiDung.NguoiDungId != user_id
            )
            .first()
        )

        if exists:

            raise HTTPException(
                status_code=400,
                detail="Email đã tồn tại"
            )

        user.Email = email

    if request.ho_ten:

        user.HoTen = request.ho_ten.strip()

    if request.so_dien_thoai:

        user.SoDienThoai = (
            request.so_dien_thoai.strip()
        )

    user.NgayCapNhat = utc_now()

    try:

        db.commit()

        db.refresh(user)

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể cập nhật"
        )

    return {

        "message":
            "Cập nhật thành công"

    }


# ============================================================
# KHÓA TÀI KHOẢN
# ============================================================

def lock_user(
    db: Session,
    user_id: int,
    ly_do_khoa: str | None = None
):

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId
            ==
            user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng"
        )

    # ========================================================
    # KHÓA VĨNH VIỄN BỞI ADMIN
    # ========================================================

    user.TrangThai = "BiKhoa"

    user.KhoaDen = None

    user.LyDoKhoa = (
        ly_do_khoa.strip()
        if ly_do_khoa
        else "Bị khóa bởi quản trị viên"
    )

    # ========================================================
    # VÔ HIỆU HÓA TOÀN BỘ JWT CŨ
    # ========================================================

    now = utc_now()

    user.TokenValidAfter = now

    user.NgayCapNhat = now

    try:

        db.commit()

        db.refresh(user)

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể khóa tài khoản"
        )

    return {

        "message":
            "Khóa tài khoản thành công",

        "nguoiDungId":
            user.NguoiDungId,

        "trangThai":
            user.TrangThai,

        "lyDoKhoa":
            user.LyDoKhoa

    }


# ============================================================
# MỞ KHÓA TÀI KHOẢN
# ============================================================

def unlock_user(
    db: Session,
    user_id: int
):

    # ========================================================
    # TÌM USER
    # ========================================================

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId
            ==
            user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng"
        )

    # ========================================================
    # KIỂM TRA USER ĐANG BỊ KHÓA
    # ========================================================

    if user.TrangThai != "BiKhoa":

        raise HTTPException(
            status_code=400,
            detail="Tài khoản chưa bị khóa"
        )

    # ========================================================
    # MỞ KHÓA
    # ========================================================

    user.TrangThai = "HoatDong"

    user.KhoaDen = None

    user.LyDoKhoa = None

    user.SoLanDangNhapSai = 0

    # ========================================================
    # THU HỒI TOKEN CŨ
    # NGƯỜI DÙNG PHẢI ĐĂNG NHẬP LẠI
    # ========================================================

    now = utc_now()

    user.TokenValidAfter = now

    user.NgayCapNhat = now

    # ========================================================
    # LƯU DATABASE
    # ========================================================

    try:

        db.commit()

        db.refresh(user)

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể mở khóa tài khoản"
        )

    # ========================================================
    # RESPONSE
    # ========================================================

    return {

        "message":
            "Mở khóa tài khoản thành công",

        "user": {

            "nguoiDungId":
                user.NguoiDungId,

            "hoTen":
                user.HoTen,

            "email":
                user.Email,

            "trangThai":
                user.TrangThai,

            "ngayCapNhat":
                user.NgayCapNhat

        }

    }