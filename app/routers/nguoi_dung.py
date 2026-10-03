from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import require_permission
from app.models.nguoi_dung import NguoiDung

from app.schemas.nguoi_dung import (
    NguoiDungCreate,
    NguoiDungUpdate,
    NguoiDungLock,
    GanVaiTroRequest,
)

from app.services.auth_service import (
    create_user,
    update_user,
    lock_user,
    unlock_user,
)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


# ============================================================
# XEM DANH SÁCH NGƯỜI DÙNG
# ============================================================

@router.get(
    "/",
    dependencies=[
        Depends(
            require_permission("USER_VIEW")
        )
    ],
)
def get_users(
    db: Session = Depends(get_db),
):
    users = (
        db.query(NguoiDung)
        .order_by(
            NguoiDung.NguoiDungId
        )
        .all()
    )

    return [
        {
            "nguoiDungId": user.NguoiDungId,
            "hoTen": user.HoTen,
            "email": user.Email,
            "soDienThoai": user.SoDienThoai,
            "trangThai": user.TrangThai,
            "ngayTao": user.NgayTao,
            "ngayCapNhat": user.NgayCapNhat,
        }
        for user in users
    ]


# ============================================================
# TẠO NGƯỜI DÙNG
# ============================================================

@router.post(
    "/",
    status_code=201,
    dependencies=[
        Depends(
            require_permission("USER_CREATE")
        )
    ],
)
def create_user_endpoint(
    request: NguoiDungCreate,
    db: Session = Depends(get_db),
):
    return create_user(
        db,
        request
    )


# ============================================================
# CẬP NHẬT NGƯỜI DÙNG
# ============================================================

@router.put(
    "/{nguoi_dung_id}",
    dependencies=[
        Depends(
            require_permission("USER_UPDATE")
        )
    ],
)
def update_user_endpoint(
    nguoi_dung_id: int,
    request: NguoiDungUpdate,
    db: Session = Depends(get_db),
):
    return update_user(
        db,
        nguoi_dung_id,
        request
    )


# ============================================================
# KHÓA TÀI KHOẢN NGƯỜI DÙNG
# ============================================================

@router.put(
    "/{nguoi_dung_id}/lock",
    dependencies=[
        Depends(
            require_permission("USER_LOCK")
        )
    ],
)
def lock_user_endpoint(
    nguoi_dung_id: int,
    request: NguoiDungLock,
    db: Session = Depends(get_db),
):
    return lock_user(
        db,
        nguoi_dung_id,
        request.ly_do_khoa
    )

# ============================================================
# MỞ KHÓA TÀI KHOẢN NGƯỜI DÙNG
# ============================================================

@router.put(
    "/{nguoi_dung_id}/unlock",
    dependencies=[
        Depends(
            require_permission("USER_UNLOCK")
        )
    ],
)
def unlock_user_endpoint(
    nguoi_dung_id: int,
    db: Session = Depends(get_db),
):
    return unlock_user(
        db,
        nguoi_dung_id
    )
# ============================================================
# GÁN VAI TRÒ CHO NGƯỜI DÙNG
# ============================================================

@router.put(
    "/{nguoi_dung_id}/assign-role",
    dependencies=[
        Depends(require_permission("USER_ASSIGN_ROLE"))
    ],
)
def assign_role_to_user(
    nguoi_dung_id: int,
    request: GanVaiTroRequest,
    db: Session = Depends(get_db),
):
    """
    API gán vai trò cho người dùng theo nguoi_dung_id
    """
    user = db.query(NguoiDung).filter(NguoiDung.NguoiDungId == nguoi_dung_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    # Cập nhật vai trò (điều chỉnh tên trường VaiTroId theo DB của dự án)
    user.VaiTroId = request.vai_tro_id
    db.commit()
    db.refresh(user)

    return {
        "message": "Gán vai trò cho người dùng thành công",
        "nguoiDungId": user.NguoiDungId,
        "vaiTroId": user.VaiTroId
    }