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

    # Decode JWT
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
    #
    # Tạm thời dùng để kiểm tra token Swagger đang gửi.
    # Sau khi xác định xong lỗi có thể xóa các dòng DEBUG này.
    #

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
        revoked_token is not None
    )

    if revoked_token:

        print(
            ">>> TOKEN BỊ TỪ CHỐI: ĐÃ CÓ TRONG RevokedToken"
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
            ">>> TOKEN BỊ TỪ CHỐI: NGƯỜI DÙNG KHÔNG TỒN TẠI"
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Người dùng không tồn tại",
        )

    # ========================================================
    # DEBUG - TOKEN VALID AFTER
    # ========================================================

    print(
        f"TokenValidAfter: {user.TokenValidAfter}"
    )

    # --------------------------------------------------------
    # Kiểm tra TokenValidAfter
    #
    # Token được tạo trước thời điểm TokenValidAfter
    # sẽ bị coi là token cũ và không được sử dụng.
    # --------------------------------------------------------

    if user.TokenValidAfter:

        # ----------------------------------------------------
        # JWT "iat" sau khi decode thường là Unix timestamp
        # nên chuyển về datetime UTC.
        # ----------------------------------------------------

        token_issued_at = datetime.fromtimestamp(
            issued_at,
            tz=timezone.utc,
        )

        valid_after = user.TokenValidAfter

        # ----------------------------------------------------
        # SQL Server DATETIME/DATETIME2 không lưu timezone.
        # Nếu không có timezone thì coi giá trị DB là UTC.
        # ----------------------------------------------------

        if valid_after.tzinfo is None:
            valid_after = valid_after.replace(
                tzinfo=timezone.utc
            )

        # ----------------------------------------------------
        # JWT iat có độ chính xác đến giây.
        # SQL Server có thể lưu microsecond.
        #
        # Vì vậy bỏ microsecond để tránh:
        #
        # iat:
        # 2026-10-01 01:20:15
        #
        # valid_after:
        # 2026-10-01 01:20:15.734821
        #
        # bị hiểu nhầm là token cũ.
        # ----------------------------------------------------

        valid_after = valid_after.replace(
            microsecond=0
        )

        # ====================================================
        # DEBUG - SO SÁNH THỜI GIAN
        # ====================================================

        print(
            f"Token issued at : {token_issued_at}"
        )

        print(
            f"Valid after     : {valid_after}"
        )

        # ----------------------------------------------------
        # Token được tạo trước TokenValidAfter
        # => token đã bị vô hiệu hóa
        # ----------------------------------------------------

        if token_issued_at < valid_after:

            print(
                ">>> TOKEN BỊ TỪ CHỐI: TOKEN CŨ HƠN TokenValidAfter"
            )

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Phiên đăng nhập đã bị thu hồi",
            )

    # ========================================================
    # TOKEN HỢP LỆ
    # ========================================================

    print(
        ">>> TOKEN HỢP LỆ"
    )

    print("=" * 60)

    return user


# LẤY USER HIỆN TẠI

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> NguoiDung:

    # Không có Authorization header

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa đăng nhập",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Lấy JWT từ Bearer
    token = credentials.credentials
    
    # Xác thực JWT--
    return verify_access_token(
        token=token,
        db=db,
    )


# KIỂM TRA QUYỀN
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
                    require_permission("QUAN_LY_TAI_KHOAN")
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

            INNER JOIN VaiTro_Quyen vtq
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

        # ====================================================
        # DEBUG - KIỂM TRA QUYỀN
        # ====================================================

        print(
            f"User {current_user.NguoiDungId} "
            f"đang yêu cầu quyền: {ma_quyen}"
        )

        print(
            "Có quyền:",
            permission is not None
        )

        # ----------------------------------------------------
        # Không có quyền
        # ----------------------------------------------------

        if not permission:

            print(
                f">>> 403 FORBIDDEN: "
                f"User {current_user.NguoiDungId} "
                f"không có quyền {ma_quyen}"
            )

            raise HTTPException(
              status_code=status.HTTP_403_FORBIDDEN,
              detail="Bạn không có quyền thực hiện chức năng này.",
            
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