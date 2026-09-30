
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from app.models.nguoi_dung import NguoiDung
from app.schemas.login import LoginRequest
from app.schemas.register import RegisterRequest

from datetime import datetime, timedelta, timezone

import jwt

from app.core.security import (
    create_access_token,
    decode_access_token
)
from app.models.revoked_token import RevokedToken


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

    # Không trả MatKhauHash ra ngoài
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
            "nguoi_dung_id":
                user.NguoiDungId
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
    new_password: str
):
    # Hash mật khẩu mới
    new_password_hash = password_hash.hash(
        new_password
    )

    # Chỉ lưu mật khẩu đã hash vào database
    user.MatKhauHash = new_password_hash
    user.NgayCapNhat = datetime.now()

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