from fastapi import (
    APIRouter,
    Depends,
    status
)

from sqlalchemy.orm import Session

from app.database import get_db

from app.schemas.login import (
    LoginRequest
)

from app.schemas.register import (
    RegisterRequest
)

from app.services.auth_service import (
    login_user,
    register_user
)


router = APIRouter(
    tags=["Authentication"]
)


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