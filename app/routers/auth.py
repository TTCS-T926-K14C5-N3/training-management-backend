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

from app.schemas.forgot_password import (
    ForgotPasswordRequest
)

from app.schemas.reset_password import (
    ResetPasswordRequest
)

from app.schemas.change_password import (
    ChangePasswordRequest
)

from app.services.auth_service import (
    login_user,
    logout_user,
    register_user,
    forgot_password,
    reset_password,
    update_password
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


# ============================================================
# ĐĂNG XUẤT
# ============================================================

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


# ============================================================
# QUÊN MẬT KHẨU
# ============================================================

@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK
)
def forgot_password_endpoint(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    return forgot_password(
        db,
        request
    )


# ============================================================
# ĐẶT LẠI MẬT KHẨU
# ============================================================

@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK
)
def reset_password_endpoint(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    return reset_password(
        db,
        request
    )


# ============================================================
# ĐỔI MẬT KHẨU
# ============================================================

@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK
)
def change_password(
    request: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    # Kiểm tra token và lấy người dùng hiện tại
    user = verify_access_token(
        token,
        db
    )

    # Đổi mật khẩu
    return update_password(
        db,
        user,
        request.current_password,
        request.new_password
    )