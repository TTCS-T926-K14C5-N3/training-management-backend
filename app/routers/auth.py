from fastapi import (
    APIRouter,
    Depends,
    status
)

from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer
)

from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import verify_access_token

from app.schemas.login import (
    LoginRequest
)

from app.schemas.register import (
    RegisterRequest
)

from app.services.auth_service import (
    login_user,
    logout_user,
    register_user
)


router = APIRouter(
    tags=["Authentication"]
)

security = HTTPBearer()

# ============================================================
# ĐĂNG KÝ
# ============================================================

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    return register_user(
        db,
        request
    )


# ============================================================
# ĐĂNG NHẬP
# ============================================================

@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    return login_user(
        db,
        request
    )

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK
)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    return logout_user(
        db,
        token
    )


# ============================================================
# KIỂM TRA PHIÊN ĐĂNG NHẬP
# ============================================================

@router.get("/me")
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    user = verify_access_token(
        token,
        db
    )

    return {
        "nguoiDungId": user.NguoiDungId,
        "hoTen": user.HoTen,
        "email": user.Email
    }