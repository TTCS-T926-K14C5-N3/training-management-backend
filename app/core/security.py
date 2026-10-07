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
    """
    Tạo JWT access token.

    Payload gồm:
    - sub: email người dùng
    - user_id: ID người dùng
    - iat: thời điểm tạo token
    - exp: thời điểm token hết hạn
    - jti: ID duy nhất của token
    """

    payload = data.copy()

    now = datetime.now(timezone.utc)

    payload.update(
        {
            # Thời điểm token được tạo
            "iat": now,

            # Thời điểm token hết hạn
            "exp": now
            + timedelta(
                minutes=ACCESS_TOKEN_EXPIRE_MINUTES
            ),

            # ID duy nhất của token
            "jti": str(uuid4()),
        }
    )

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


# ============================================================
# LÀM MỚI ACCESS TOKEN
# ============================================================

def refresh_access_token(
    token: str,
    db: Session,
) -> str:
    """
    Kiểm tra token hiện tại rồi tạo token mới.

    Token cũ phải:
    - hợp lệ
    - chưa hết hạn
    - chưa bị revoke
    - người dùng vẫn tồn tại
    """

    user = verify_access_token(
        token,
        db,
    )

    new_token = create_access_token(
        {
            "sub": user.Email,
            "user_id": user.NguoiDungId,
        }
    )

    return new_token


# ============================================================
# GIẢI MÃ ACCESS TOKEN
# ============================================================

def decode_access_token(token: str) -> dict:
    """
    Giải mã và kiểm tra chữ ký JWT.

    PyJWT sẽ tự kiểm tra:
    - chữ ký
    - thuật toán
    - exp nếu token đã hết hạn
    """

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
    """
    Xác thực access token và trả về người dùng hiện tại.

    Kiểm tra:
    1. JWT hợp lệ
    2. Token chưa hết hạn
    3. JWT có user_id, jti, iat
    4. Token chưa nằm trong RevokedToken
    5. Người dùng còn tồn tại
    """

    # --------------------------------------------------------
    # Decode JWT
    # --------------------------------------------------------

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

    # ========================================================
    # DEBUG - THÔNG TIN TOKEN
    # ========================================================

    print("=" * 60)
    print("KIỂM TRA ACCESS TOKEN")
    print(f"User ID       : {user_id}")
    print(f"JTI           : {jti}")
    print(f"Issued At     : {issued_at}")
    print("=" * 60)

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

    # ========================================================
    # DEBUG - KIỂM TRA REVOKED TOKEN
    # ========================================================

    print(
        "Token có trong RevokedToken:",
        revoked_token is not None,
    )

    if revoked_token:
        print(
            ">>> TOKEN BỊ TỪ CHỐI: "
            "ĐÃ CÓ TRONG RevokedToken"
        )

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
        print(
            ">>> TOKEN BỊ TỪ CHỐI: "
            "NGƯỜI DÙNG KHÔNG TỒN TẠI"
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Người dùng không tồn tại",
        )

    # ========================================================
    # TOKEN HỢP LỆ
    # ========================================================

    print(
        ">>> TOKEN HỢP LỆ"
    )

    print("=" * 60)

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
    """
    Lấy người dùng hiện tại từ Authorization: Bearer <token>.
    """

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
            ],
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

        permission_query = text(
            """
            SELECT TOP 1
                q.QuyenId
            FROM Quyen q

            INNER JOIN VaiTro_Quyen vtq
                ON q.QuyenId = vtq.QuyenId

            INNER JOIN NguoiDung_VaiTro ndvt
                ON vtq.VaiTroId = ndvt.VaiTroId

            WHERE ndvt.NguoiDungId = :nguoi_dung_id
              AND q.MaQuyen = :ma_quyen
            """
        )

        permission = db.execute(
            permission_query,
            {
                "nguoi_dung_id": current_user.NguoiDungId,
                "ma_quyen": ma_quyen,
            },
        ).first()

        # ====================================================
        # DEBUG - KIỂM TRA QUYỀN
        # ====================================================

        print(
            f"User {current_user.NguoiDungId} "
            f"đang yêu cầu quyền: {ma_quyen}"
        )

        print(
            "Có quyền:",
            permission is not None,
        )

        # ----------------------------------------------------
        # Không có quyền
        # ----------------------------------------------------

        if not permission:
            print(
                ">>> 403 FORBIDDEN: "
                f"User {current_user.NguoiDungId} "
                f"không có quyền {ma_quyen}"
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Bạn không có quyền "
                    "thực hiện chức năng này."
                ),
            )

        # ----------------------------------------------------
        # Có quyền
        # ----------------------------------------------------

        print(
            f">>> 200: User {current_user.NguoiDungId} "
            f"có quyền {ma_quyen}"
        )

        return current_user

    return permission_checker