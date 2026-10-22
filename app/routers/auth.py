
from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    UploadFile,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import (
    verify_access_token,
    get_current_user as get_current_user_dependency,
    require_permission,
    refresh_access_token,
)
from app.models.nguoi_dung import NguoiDung
from app.schemas.login import LoginRequest
from app.schemas.update_profile import UpdateProfileRequest
from app.schemas.activate_account import ActivateAccountRequest
from app.schemas.resend_activation import ResendActivationRequest
from app.schemas.forgot_password import ForgotPasswordRequest
from app.schemas.reset_password import ResetPasswordRequest
from app.schemas.change_password import ChangePasswordRequest
from app.services.auth_service import (
    login_user,
    logout_user,
    forgot_password,
    reset_password,
    update_password,
    activate_account,
    _get_role_names,
    _role_home_path,
    resend_activation,
)
from app.services.profile_service import update_my_profile
from app.services.avatar_service import (
    avatar_url_for_user,
    save_avatar,
)


router = APIRouter(tags=["Authentication"])

security = HTTPBearer()


# ============================================================
# DANG NHAP
# ============================================================

@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    response = login_user(db, request)

    response["avatarUrl"] = avatar_url_for_user(
        response["nguoiDungId"]
    )

    return response


# ============================================================
# LAM MOI ACCESS TOKEN
# ============================================================

@router.post("/refresh")
def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    new_token = refresh_access_token(
        credentials.credentials,
        db,
    )

    return {
        "access_token": new_token,
        "token_type": "bearer",
    }


# ============================================================
# DANG XUAT
# ============================================================

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    return logout_user(
        db,
        credentials.credentials,
    )


# ============================================================
# THONG TIN NGUOI DUNG HIEN TAI
# ============================================================

@router.get("/me")
def get_current_user(
    current_user: NguoiDung = Depends(
        get_current_user_dependency
    ),
):
    return {
        "nguoiDungId": current_user.NguoiDungId,
        "hoTen": current_user.HoTen,
        "email": current_user.Email,
        "soDienThoai": current_user.SoDienThoai,
        "ngaySinh": (
            current_user.NgaySinh.isoformat()
            if current_user.NgaySinh
            else None
        ),
        "diaChi": current_user.DiaChi,
        "avatarUrl": avatar_url_for_user(
            current_user.NguoiDungId
        ),
    }


# ============================================================
# CAP NHAT ANH DAI DIEN
# ============================================================

@router.put("/me/avatar")
async def update_current_user_avatar(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    user = verify_access_token(
        credentials.credentials,
        db,
    )

    image_data = await file.read(2 * 1024 * 1024 + 1)
    avatar_path = save_avatar(
        user.NguoiDungId,
        image_data,
    )

    return {
        "message": "Cập nhật ảnh đại diện thành công",
        "avatarUrl": avatar_url_for_user(user.NguoiDungId),
        "thumbnailWidth": 256,
        "thumbnailHeight": 256,
        "sizeBytes": avatar_path.stat().st_size,
    }


# ============================================================
# CAP NHAT HO SO NGUOI DUNG
# ============================================================

@router.put("/me")
def update_current_user_profile(
    request: UpdateProfileRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    user = verify_access_token(
        credentials.credentials,
        db,
    )

    updated_user = update_my_profile(
        db=db,
        current_user=user,
        data=request,
    )

    return {
        "message": "Cập nhật hồ sơ thành công",
        "data": {
            "nguoiDungId": updated_user.NguoiDungId,
            "hoTen": updated_user.HoTen,
            "email": updated_user.Email,
            "soDienThoai": updated_user.SoDienThoai,
            "ngaySinh": (
                updated_user.NgaySinh.isoformat()
                if updated_user.NgaySinh
                else None
            ),
            "diaChi": updated_user.DiaChi,
            "avatarUrl": avatar_url_for_user(
                updated_user.NguoiDungId
            ),
        },
    }


# ============================================================
# QUEN MAT KHAU
# ============================================================

@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
)
def forgot_password_endpoint(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    return forgot_password(db, request)


@router.post(
    "/resend-activation",
    status_code=status.HTTP_200_OK,
)
def resend_activation_endpoint(
    request: ResendActivationRequest,
    db: Session = Depends(get_db),
):
    return resend_activation(db, request)


# ============================================================
# KIEM TRA TOKEN DAT LAI MAT KHAU
# ============================================================

@router.get("/reset-password/validate-token")
def validate_reset_token_endpoint(
    token: str = Query(
        min_length=20,
        max_length=255,
        description="Token đặt lại mật khẩu",
    ),
    db: Session = Depends(get_db),
):
    from app.services.auth_service import validate_reset_token

    return validate_reset_token(db, token)


# ============================================================
# DAT LAI MAT KHAU
# ============================================================

@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
)
def reset_password_endpoint(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    return reset_password(db, request)


# ============================================================
# DOI MAT KHAU
# ============================================================

@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
)
def change_password(
    request: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    user = verify_access_token(
        credentials.credentials,
        db,
    )

    result = update_password(
        db,
        user,
        request.current_password,
        request.new_password,
    )

    # Neu service tra ve dict, giu lai thong tin do.
    response = (
        result.copy()
        if isinstance(result, dict)
        else {
            "message": "Cập nhật mật khẩu thành công"
        }
    )

    # Them duong dan trang chu theo vai tro.
    response["trangChuTheoVaiTro"] = _role_home_path(
        _get_role_names(db, user.NguoiDungId)
    )

    return response


# ============================================================
# KIEM TRA PHAN QUYEN
# ============================================================

@router.get(
    "/test-permission",
    dependencies=[
        Depends(require_permission("USER_CREATE"))
    ],
)
def test_permission():
    return {
        "message": "Bạn có quyền USER_CREATE"
    }


# ============================================================
# KICH HOAT TAI KHOAN
# ============================================================

@router.post("/activate-account")
def activate_account_endpoint(
    request: ActivateAccountRequest,
    db: Session = Depends(get_db),
):
    return activate_account(
        db,
        request.token,
    )
