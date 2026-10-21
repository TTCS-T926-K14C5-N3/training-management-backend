import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    SECRET_KEY,
)
from app.database import get_db
from app.models.nguoi_dung import NguoiDung
from app.models.revoked_token import RevokedToken


logger = logging.getLogger("app.core.security")

bearer_scheme = HTTPBearer(auto_error=False)


class TokenPayload(dict):
    """Payload của JWT access token."""


def create_access_token(data: dict) -> str:
    payload = data.copy()
    now = datetime.now(timezone.utc)

    payload.update({
        "iat": now.timestamp(),
        "exp": now + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),
        "jti": str(uuid4()),
    })

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def refresh_access_token(token: str, db: Session) -> str:
    user = verify_access_token(token, db)

    return create_access_token({
        "sub": user.Email,
        "user_id": user.NguoiDungId,
    })


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )


def verify_access_token(
    token: str,
    db: Session,
) -> NguoiDung:
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token hết hạn",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ",
        )

    user_id = payload.get("user_id")
    jti = payload.get("jti")
    issued_at = payload.get("iat")

    if user_id is None or not jti or issued_at is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ",
        )

    logger.debug(
        "Kiểm tra access token: user_id=%s jti=%s",
        user_id,
        jti,
    )

    # Kiểm tra token đã bị thu hồi.
    revoked_token = (
        db.query(RevokedToken)
        .filter(RevokedToken.Jti == jti)
        .first()
    )

    if revoked_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã bị thu hồi",
        )

    # Tìm người dùng.
    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Người dùng không tồn tại",
        )

    # Giữ kiểm tra khóa tài khoản từ origin/main.
    if user.TrangThai == "BiKhoa":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Tài khoản đã bị khóa; "
                "phiên đăng nhập đã bị thu hồi"
            ),
        )

    # Vô hiệu hóa token cũ sau khi đổi mật khẩu
    # hoặc khi TokenValidAfter được cập nhật.
    if user.TokenValidAfter is not None:
        token_issued_at = datetime.fromtimestamp(
            float(issued_at),
            tz=timezone.utc,
        )

        valid_after = user.TokenValidAfter

        # TokenValidAfter is stored as a naive UTC datetime.
        if valid_after.tzinfo is None:
            valid_after = valid_after.replace(tzinfo=timezone.utc)

        valid_after = valid_after.astimezone(timezone.utc)

        logger.debug(
            "Token issued at=%s, valid after=%s",
            token_issued_at,
            valid_after,
        )

        if token_issued_at < valid_after:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Phiên đăng nhập đã bị thu hồi",
            )

    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> NguoiDung:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa đăng nhập",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_access_token(
        token=credentials.credentials,
        db=db,
    )


def require_permission(ma_quyen: str):
    """Dependency kiểm tra quyền truy cập API."""

    def permission_checker(
        current_user: NguoiDung = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> NguoiDung:
        permission_query = text("""
            SELECT TOP 1 1
            FROM NguoiDung_VaiTro ndvt
            INNER JOIN VaiTro vt
                ON vt.VaiTroId = ndvt.VaiTroId
            WHERE ndvt.NguoiDungId = :nguoi_dung_id
              AND (
                    ndvt.VaiTroId = 8
                    OR LOWER(LTRIM(RTRIM(vt.TenVaiTro))) IN (
                        N'admin',
                        N'quản trị hệ thống',
                        N'quản trị viên hệ thống'
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM VaiTro_Quyen vtq
                        INNER JOIN Quyen q
                            ON q.QuyenId = vtq.QuyenId
                        WHERE vtq.VaiTroId = ndvt.VaiTroId
                          AND q.MaQuyen = :ma_quyen
                    )
              )
        """)

        permission = db.execute(
            permission_query,
            {
                "nguoi_dung_id": current_user.NguoiDungId,
                "ma_quyen": ma_quyen,
            },
        ).first()

        logger.debug(
            "User %s yêu cầu quyền %s; có quyền=%s",
            current_user.NguoiDungId,
            ma_quyen,
            permission is not None,
        )

        if not permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Bạn không có quyền "
                    "thực hiện chức năng này."
                ),
            )

        return current_user

    return permission_checker