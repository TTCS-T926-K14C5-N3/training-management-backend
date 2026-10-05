from enum import Enum, IntEnum

from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from sqlalchemy.orm import Session

from app.database import get_db

from app.core.security import (
    require_permission,
    get_current_user,
)

from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro

from app.schemas.nguoi_dung import (
    NguoiDungCreate,
    NguoiDungUpdate,
    NguoiDungLock,
    NguoiDungResponse,
)

from app.services.auth_service import (
    create_user,
    update_user,
    lock_user,
    unlock_user,
)


# =========================================================
# ENUM TRẠNG THÁI NGƯỜI DÙNG
# =========================================================

class TrangThaiNguoiDung(str, Enum):
    HOAT_DONG = "HoatDong"
    BI_KHOA = "BiKhoa"


# =========================================================
# ENUM ID VAI TRÒ
#
# Giới hạn role_id chỉ được phép từ 1 đến 8.
# Swagger sẽ hiển thị danh sách lựa chọn.
# =========================================================

class VaiTroId(IntEnum):
    GUEST = 1
    STUDENT = 2
    INSTRUCTOR = 3
    TA = 4
    ADMISSIONS = 5
    ACCOUNTANT = 6
    TRAINING_MANAGER = 7
    ADMIN = 8


# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


# =========================================================
# LẤY THÔNG TIN NGƯỜI DÙNG HIỆN TẠI
# GET /users/me
# =========================================================

@router.get(
    "/me",
    response_model=NguoiDungResponse,
)
def get_me(
    current_user: NguoiDung = Depends(get_current_user),
):
    user_role = getattr(
        current_user,
        "vai_tro",
        "STUDENT",
    )

    user_permissions = []

    if hasattr(
        current_user,
        "get_permissions",
    ):
        user_permissions = current_user.get_permissions()

    elif hasattr(
        current_user,
        "permissions",
    ):
        user_permissions = [
            p.ten_quyen
            for p in current_user.permissions
        ]

    return NguoiDungResponse(
        id=current_user.NguoiDungId,
        ho_ten=current_user.HoTen,
        email=current_user.Email,
        so_dien_thoai=current_user.SoDienThoai,
        trang_thai=current_user.TrangThai,
        role=str(user_role),
        permissions=user_permissions,
    )


# =========================================================
# LẤY DANH SÁCH NGƯỜI DÙNG
#
# GET /users/
#
# Hỗ trợ:
# - Tìm kiếm theo họ tên
# - Tìm kiếm theo email
# - Tìm kiếm theo số điện thoại
# - Lọc theo vai trò
# - Lọc theo trạng thái
# - Kết hợp các bộ lọc
# - Phân trang
# - Mặc định 20 người/trang
# =========================================================

@router.get(
    "/",
    dependencies=[
        Depends(
            require_permission("USER_VIEW")
        )
    ],
)
def get_users(
    search: str | None = Query(
        default=None,
        description=(
            "Tìm kiếm theo họ tên, email "
            "hoặc số điện thoại"
        ),
    ),

    role_id: VaiTroId | None = Query(
        default=None,
        description="Lọc người dùng theo vai trò",
    ),

    status: TrangThaiNguoiDung | None = Query(
        default=None,
        description="Lọc theo trạng thái tài khoản",
    ),

    page: int = Query(
        default=1,
        ge=1,
        description="Số trang",
    ),

    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Số người dùng mỗi trang",
    ),

    db: Session = Depends(get_db),
):
    # =====================================================
    # QUERY CƠ BẢN
    # =====================================================

    query = db.query(NguoiDung)

    # =====================================================
    # TÌM KIẾM
    #
    # Họ tên / Email / Số điện thoại
    # =====================================================

    if search:
        search_value = search.strip()

        if search_value:
            search_pattern = f"%{search_value}%"

            query = query.filter(
                (NguoiDung.HoTen.ilike(search_pattern))
                |
                (NguoiDung.Email.ilike(search_pattern))
                |
                (
                    NguoiDung.SoDienThoai.ilike(
                        search_pattern
                    )
                )
            )

    # =====================================================
    # LỌC THEO VAI TRÒ
    #
    # Một người dùng có thể có nhiều vai trò.
    # Sử dụng bảng NguoiDung_VaiTro.
    # =====================================================

    if role_id is not None:
        query = query.filter(
            NguoiDung.NguoiDungId.in_(
                db.query(
                    NguoiDungVaiTro.NguoiDungId
                ).filter(
                    NguoiDungVaiTro.VaiTroId == int(role_id)
                )
            )
        )

    # =====================================================
    # LỌC THEO TRẠNG THÁI
    #
    # Chỉ cho phép:
    # - HoatDong
    # - BiKhoa
    # =====================================================

    if status is not None:
        query = query.filter(
            NguoiDung.TrangThai == status.value
        )

    # =====================================================
    # TỔNG SỐ BẢN GHI SAU KHI LỌC
    # =====================================================

    total = query.count()

    # =====================================================
    # PHÂN TRANG
    # =====================================================

    offset = (page - 1) * limit

    users = (
        query
        .order_by(
            NguoiDung.NguoiDungId
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    # =====================================================
    # TRẢ VỀ KẾT QUẢ
    # =====================================================

    return {
        "data": [
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
        ],

        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (
                (total + limit - 1) // limit
                if total > 0
                else 0
            ),
        },
    }


# =========================================================
# TẠO NGƯỜI DÙNG
# POST /users/
# =========================================================

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
        request,
    )


# =========================================================
# CẬP NHẬT NGƯỜI DÙNG
# PUT /users/{nguoi_dung_id}
# =========================================================

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
        request,
    )


# =========================================================
# KHÓA NGƯỜI DÙNG
# PUT /users/{nguoi_dung_id}/lock
# =========================================================

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
        request,
    )


# =========================================================
# MỞ KHÓA NGƯỜI DÙNG
# PUT /users/{nguoi_dung_id}/unlock
# =========================================================

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
        nguoi_dung_id,
    )