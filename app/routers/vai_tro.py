from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import (
    get_current_user,
    require_permission,
)

from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.vai_tro import VaiTro


router = APIRouter(
    prefix="/roles",
    tags=["Roles"],
)


# ============================================================
# LẤY DANH SÁCH VAI TRÒ
# ============================================================

@router.get(
    "/",
    dependencies=[
        Depends(require_permission("ROLE_VIEW"))
    ],
)
def get_roles(
    db: Session = Depends(get_db),
):
    roles = (
        db.query(VaiTro)
        .filter(VaiTro.VaiTroId <= 8)
        .order_by(VaiTro.VaiTroId)
        .all()
    )

    return [
        {
            "vaiTroId": role.VaiTroId,
            "tenVaiTro": role.TenVaiTro,
            "moTa": role.MoTa,
        }
        for role in roles
    ]


# ============================================================
# LẤY VAI TRÒ CỦA MỘT NGƯỜI DÙNG
# ============================================================

@router.get(
    "/users/{nguoi_dung_id}",
    dependencies=[
        Depends(require_permission("ROLE_VIEW"))
    ],
)
def get_user_roles(
    nguoi_dung_id: int,
    db: Session = Depends(get_db),
):
    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId == nguoi_dung_id
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Người dùng không tồn tại.",
        )

    rows = (
        db.query(
            NguoiDungVaiTro,
            VaiTro,
        )
        .join(
            VaiTro,
            VaiTro.VaiTroId
            == NguoiDungVaiTro.VaiTroId,
        )
        .filter(
            NguoiDungVaiTro.NguoiDungId
            == nguoi_dung_id,
            VaiTro.VaiTroId <= 8,
        )
        .order_by(VaiTro.VaiTroId)
        .all()
    )

    return [
        {
            "vaiTroId": role.VaiTroId,
            "tenVaiTro": role.TenVaiTro,
            "moTa": role.MoTa,
            "ngayGan": user_role.NgayGan,
        }
        for user_role, role in rows
    ]


# ============================================================
# GÁN VAI TRÒ
# ============================================================

@router.post(
    "/users/{nguoi_dung_id}/{vai_tro_id}",
    dependencies=[
        Depends(require_permission("ROLE_UPDATE"))
    ],
)
def assign_role(
    nguoi_dung_id: int,
    vai_tro_id: int,
    db: Session = Depends(get_db),
):
    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId == nguoi_dung_id
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Người dùng không tồn tại.",
        )

    role = (
        db.query(VaiTro)
        .filter(
            VaiTro.VaiTroId == vai_tro_id,
            VaiTro.VaiTroId <= 8,
        )
        .first()
    )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vai trò không tồn tại.",
        )

    existing = (
        db.query(NguoiDungVaiTro)
        .filter(
            NguoiDungVaiTro.NguoiDungId
            == nguoi_dung_id,
            NguoiDungVaiTro.VaiTroId
            == vai_tro_id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Người dùng đã có vai trò này.",
        )

    user_role = NguoiDungVaiTro(
        NguoiDungId=nguoi_dung_id,
        VaiTroId=vai_tro_id,
        NgayGan=datetime.now(),
    )

    db.add(user_role)
    db.commit()

    return {
        "message": "Gán vai trò thành công.",
        "nguoiDungId": nguoi_dung_id,
        "vaiTroId": vai_tro_id,
        "tenVaiTro": role.TenVaiTro,
    }


# ============================================================
# THU HỒI VAI TRÒ
# ============================================================

@router.delete(
    "/users/{nguoi_dung_id}/{vai_tro_id}",
    dependencies=[
        Depends(require_permission("ROLE_DELETE"))
    ],
)
def remove_role(
    nguoi_dung_id: int,
    vai_tro_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # --------------------------------------------------------
    # KHÔNG CHO ADMIN TỰ THU HỒI VAI TRÒ ADMIN CỦA CHÍNH MÌNH
    # --------------------------------------------------------

    if current_user.NguoiDungId == nguoi_dung_id:
        role = (
            db.query(VaiTro)
            .filter(
                VaiTro.VaiTroId == vai_tro_id
            )
            .first()
        )

        if role and role.TenVaiTro.lower() in [
            "admin",
            "quản trị hệ thống",
            "quản trị viên",
        ]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Không thể tự thu hồi "
                    "vai trò quản trị của chính mình."
                ),
            )

    user_role = (
        db.query(NguoiDungVaiTro)
        .filter(
            NguoiDungVaiTro.NguoiDungId
            == nguoi_dung_id,
            NguoiDungVaiTro.VaiTroId
            == vai_tro_id,
        )
        .first()
    )

    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Người dùng không có vai trò này.",
        )

    db.delete(user_role)
    db.commit()

    return {
        "message": "Thu hồi vai trò thành công.",
        "nguoiDungId": nguoi_dung_id,
        "vaiTroId": vai_tro_id,
    }