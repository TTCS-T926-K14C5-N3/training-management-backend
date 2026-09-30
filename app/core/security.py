from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from fastapi import (
    HTTPException,
    status
)

from sqlalchemy.orm import Session

from app.models.nguoi_dung import NguoiDung
from app.models.revoked_token import RevokedToken


# ============================================================
# JWT CONFIG
# ============================================================

SECRET_KEY = "training-management-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# ============================================================
# TẠO ACCESS TOKEN
# ============================================================

def create_access_token(data: dict) -> str:
    payload = data.copy()

    now = datetime.now(timezone.utc)

    payload.update({
        # Thời điểm token được tạo
        "iat": now,

        # Thời điểm token hết hạn
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),

        # ID duy nhất của token
        "jti": str(uuid4())
    })

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


# ============================================================
# GIẢI MÃ ACCESS TOKEN
# ============================================================

def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM]
    )


# ============================================================
# XÁC THỰC ACCESS TOKEN
# ============================================================

def verify_access_token(
    token: str,
    db: Session
) -> NguoiDung:

    # --------------------------------------------------------
    # Decode JWT
    # --------------------------------------------------------

    try:
        payload = decode_access_token(token)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã hết hạn"
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ"
        )

    # --------------------------------------------------------
    # Lấy dữ liệu từ JWT
    # --------------------------------------------------------

    user_id = payload.get("user_id")
    jti = payload.get("jti")
    issued_at = payload.get("iat")

    if not user_id or not jti or not issued_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ"
        )

    # --------------------------------------------------------
    # Kiểm tra token đã bị revoke khi logout chưa
    # --------------------------------------------------------

    revoked_token = (
        db.query(RevokedToken)
        .filter(
            RevokedToken.Jti == jti
        )
        .first()
    )

    if revoked_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã bị thu hồi"
        )

    # --------------------------------------------------------
    # Tìm người dùng
    # --------------------------------------------------------

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId == user_id
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Người dùng không tồn tại"
        )

    # --------------------------------------------------------
    # Kiểm tra token có được tạo trước lần đổi mật khẩu không
    # --------------------------------------------------------

    if user.TokenValidAfter:

        token_issued_at = datetime.fromtimestamp(
            issued_at,
            tz=timezone.utc
        )

        valid_after = user.TokenValidAfter

        # SQL Server DATETIME2 không lưu timezone
        if valid_after.tzinfo is None:
            valid_after = valid_after.replace(
                tzinfo=timezone.utc
            )

        # Token được cấp trước khi đổi mật khẩu
        # => token không còn hợp lệ
        if token_issued_at < valid_after:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Phiên đăng nhập đã bị thu hồi"
            )

    # --------------------------------------------------------
    # Token hợp lệ
    # --------------------------------------------------------

    return user