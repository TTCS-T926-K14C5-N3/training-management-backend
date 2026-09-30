from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from fastapi import (
    Depends,
    HTTPException,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.nguoi_dung import NguoiDung
from app.models.revoked_token import RevokedToken


# ============================================================
# JWT CONFIG
# ============================================================

SECRET_KEY = "training-management-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# ============================================================
# BEARER AUTHENTICATION
# ============================================================

bearer_scheme = HTTPBearer(
    auto_error=False
)


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
        "jti": str(uuid4()),
    })

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


# ============================================================
# GIẢI MÃ ACCESS TOKEN
# ============================================================

def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )


# ============================================================
# XÁC THỰC ACCESS TOKEN
# ============================================================

def verify_access_token(
    token: str,
    db: Session,
) -> NguoiDung:

    # --------------------------------------------------------
    # Decode JWT
    # --------------------------------------------------------

    try:
        payload = decode_access_token(token)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã hết hạn",
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ",
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
            detail="Token không hợp lệ",
        )

    # --------------------------------------------------------
    # Kiểm tra token đã bị revoke chưa
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
            detail="Phiên đăng nhập đã bị thu hồi",
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
            detail="Người dùng không tồn tại",
        )

    # --------------------------------------------------------
    # Kiểm tra TokenValidAfter
    #
    # Token được tạo trước thời điểm TokenValidAfter
    # sẽ bị coi là token cũ và không được sử dụng.
    # --------------------------------------------------------

    if user.TokenValidAfter:

        # JWT "iat" sau khi decode thường là Unix timestamp
        # nên chuyển về datetime UTC.
        token_issued_at = datetime.fromtimestamp(
            issued_at,
            tz=timezone.utc,
        )

        valid_after = user.TokenValidAfter

        # SQL Server DATETIME/DATETIME2 không lưu timezone.
        # Nếu không có timezone thì coi giá trị DB là UTC.
        if valid_after.tzinfo is None:
            valid_after = valid_after.replace(
                tzinfo=timezone.utc
            )

        # ----------------------------------------------------
        # QUAN TRỌNG:
        #
        # JWT iat chỉ có độ chính xác đến giây.
        # TokenValidAfter có thể có microsecond.
        #
        # Ví dụ:
        #
        # iat:
        # 2026-10-01 01:20:15
        #
        # TokenValidAfter:
        # 2026-10-01 01:20:15.734821
        #
        # Nếu không bỏ microsecond thì token mới có thể
        # bị hiểu nhầm là token cũ.
        # ----------------------------------------------------

        valid_after = valid_after.replace(
            microsecond=0
        )

        # ----------------------------------------------------
        # Token được tạo trước TokenValidAfter
        # => token đã bị vô hiệu hóa
        # ----------------------------------------------------

        if token_issued_at < valid_after:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Phiên đăng nhập đã bị thu hồi",
            )

    return user


# ============================================================
# LẤY USER HIỆN TẠI
# ============================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> NguoiDung:

    # --------------------------------------------------------
    # Không có Authorization header
    # --------------------------------------------------------

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa đăng nhập",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    # --------------------------------------------------------
    # Lấy JWT từ Bearer
    # --------------------------------------------------------

    token = credentials.credentials

    # --------------------------------------------------------
    # Xác thực JWT
    # --------------------------------------------------------

    return verify_access_token(
        token=token,
        db=db,
    )


# ============================================================
# KIỂM TRA QUYỀN
# ============================================================

def require_permission(
    ma_quyen: str,
):
    """
    Dependency dùng để kiểm tra người dùng có quyền hay không.

    Ví dụ:

        @router.post(
            "/users",
            dependencies=[
                Depends(
                    require_permission("USER_CREATE")
                )
            ]
        )

    Có quyền:
        API được phép chạy.

    Không có quyền:
        HTTP 403.
    """

    def permission_checker(
        current_user: NguoiDung = Depends(
            get_current_user
        ),
        db: Session = Depends(
            get_db
        ),
    ) -> NguoiDung:

        # ----------------------------------------------------
        # Kiểm tra quyền qua quan hệ:
        #
        # NguoiDung
        #      ↓
        # NguoiDung_VaiTro
        #      ↓
        # VaiTro
        #      ↓
        # VaiTroQuyen
        #      ↓
        # Quyen
        # ----------------------------------------------------

        permission_query = text("""
            SELECT TOP 1
                q.QuyenId
            FROM Quyen q

            INNER JOIN VaiTroQuyen vtq
                ON q.QuyenId = vtq.QuyenId

            INNER JOIN NguoiDung_VaiTro ndvt
                ON vtq.VaiTroId = ndvt.VaiTroId

            WHERE ndvt.NguoiDungId = :nguoi_dung_id
              AND q.MaQuyen = :ma_quyen
        """)

        permission = db.execute(
            permission_query,
            {
                "nguoi_dung_id": current_user.NguoiDungId,
                "ma_quyen": ma_quyen,
            },
        ).first()

        # ----------------------------------------------------
        # Không có quyền
        # ----------------------------------------------------

        if not permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Bạn không có quyền thực hiện "
                    f"chức năng này: {ma_quyen}"
                ),
            )

        # ----------------------------------------------------
        # Có quyền
        # ----------------------------------------------------

        return current_user

    return permission_checker