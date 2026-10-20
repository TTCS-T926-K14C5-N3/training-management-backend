from enum import Enum, IntEnum

from fastapi import (
    APIRouter,
    Depends,
    Query,
    UploadFile,
    File,
    HTTPException,
)
from pydantic import EmailStr
from sqlalchemy import String, cast, or_
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db

from app.core.security import (
    require_permission,
    get_current_user,
)

from app.models.nguoi_dung import NguoiDung
from app.models.admissions import LeadConversion
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.vai_tro import VaiTro

from app.schemas.admin_create_user import (
    AdminCreateUserRequest,
)

from app.schemas.nguoi_dung import (
    NguoiDungCreate,
    NguoiDungUpdate,
    NguoiDungLock,
    NguoiDungResponse,
)

from app.services.auth_service import (
    admin_create_user,
    create_user,
    update_user,
    lock_user,
    unlock_user,
    delete_user,
)

from app.services.user_import_service import (
    preview_user_import,
    import_valid_users,
)
from app.services.avatar_service import (
    avatar_path_for_user,
    avatar_url_for_user,
)


# =========================================================
# ENUM TRẠNG THÁI NGƯỜI DÙNG
# =========================================================

class TrangThaiNguoiDung(str, Enum):
    HOAT_DONG = "HoatDong"
    BI_KHOA = "BiKhoa"


# =========================================================
# ENUM ID VAI TRÒ
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
#
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
        avatar_url=avatar_url_for_user(
            current_user.NguoiDungId
        ),
    )


@router.get(
    "/{nguoi_dung_id}/avatar",
    dependencies=[Depends(get_current_user)],
    responses={
        200: {
            "content": {
                "image/jpeg": {},
            },
        },
    },
)
def get_user_avatar(nguoi_dung_id: int):
    avatar_path = avatar_path_for_user(nguoi_dung_id)

    if not avatar_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Người dùng chưa tải ảnh đại diện.",
        )

    return Response(
        content=avatar_path.read_bytes(),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, max-age=86400",
        },
    )


# =========================================================
# KIỂM TRA EMAIL ĐÃ TỒN TẠI CHƯA
#
# GET /users/check-email?email=...
#
# Dùng cho popup tạo tài khoản: hiển thị cảnh báo đỏ
# ngay dưới ô email trước khi bấm tạo.
# =========================================================

@router.get(
    "/check-email",
    dependencies=[
        Depends(
            require_permission("USER_CREATE")
        )
    ],
)
def check_email_exists(
    email: EmailStr = Query(
        description="Email cần kiểm tra",
    ),
    db: Session = Depends(get_db),
):
    normalized_email = str(email).strip().lower()

    exists = (
        db.query(NguoiDung.NguoiDungId)
        .filter(NguoiDung.Email == normalized_email)
        .first()
        is not None
    )

    return {
        "email": normalized_email,
        "exists": exists,
        "message": (
            "Email đã tồn tại"
            if exists
            else "Email hợp lệ"
        ),
    }


# =========================================================
# LẤY DANH SÁCH NGƯỜI DÙNG
# GET /users/
#
# Hỗ trợ:
# - Tìm kiếm họ tên
# - Tìm kiếm email
# - Tìm kiếm số điện thoại
# - Lọc vai trò
# - Lọc trạng thái
# - Phân trang
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
    # =====================================================

    if search:
        search_value = search.strip()

        if search_value:
            search_pattern = f"%{search_value}%"

            query = query.filter(
                or_(
                    NguoiDung.HoTen.ilike(search_pattern),
                    NguoiDung.Email.ilike(search_pattern),
                    NguoiDung.SoDienThoai.ilike(search_pattern),
                    cast(NguoiDung.NguoiDungId, String).ilike(search_pattern),
                    NguoiDung.NguoiDungId.in_(
                        db.query(LeadConversion.NguoiDungId).filter(
                            LeadConversion.MaHocVien.ilike(search_pattern)
                        )
                    ),
                )
            )

    # =====================================================
    # LỌC THEO VAI TRÒ
    #
    # Một người dùng có thể có nhiều vai trò.
    # =====================================================

    if role_id is not None:
        query = query.filter(
            NguoiDung.NguoiDungId.in_(
                db.query(
                    NguoiDungVaiTro.NguoiDungId
                ).filter(
                    NguoiDungVaiTro.VaiTroId
                    == int(role_id)
                )
            )
        )

    # =====================================================
    # LỌC THEO TRẠNG THÁI
    # =====================================================

    if status is not None:
        query = query.filter(
            NguoiDung.TrangThai
            == status.value
        )

    # =====================================================
    # TỔNG SỐ BẢN GHI
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

    role_rows = (
        db.query(
            NguoiDungVaiTro.NguoiDungId,
            NguoiDungVaiTro.VaiTroId,
            VaiTro.TenVaiTro,
        )
        .join(
            VaiTro,
            VaiTro.VaiTroId == NguoiDungVaiTro.VaiTroId,
        )
        .filter(
            NguoiDungVaiTro.NguoiDungId.in_(
                [user.NguoiDungId for user in users]
            )
        )
        .order_by(
            NguoiDungVaiTro.NguoiDungId,
            NguoiDungVaiTro.VaiTroId,
        )
        .all()
    ) if users else []

    roles_by_user: dict[int, list[str]] = {}
    role_ids_by_user: dict[int, list[int]] = {}
    for user_id, role_id, role_name in role_rows:
        roles_by_user.setdefault(user_id, []).append(role_name)
        role_ids_by_user.setdefault(user_id, []).append(role_id)

    # =====================================================
    # TRẢ VỀ
    # =====================================================

    return {
        "data": [
            {
                "nguoiDungId": user.NguoiDungId,
                "hoTen": user.HoTen,
                "email": user.Email,
                "soDienThoai": user.SoDienThoai,
                "avatarUrl": avatar_url_for_user(
                    user.NguoiDungId
                ),
                "trangThai": user.TrangThai,
                "vaiTro": ", ".join(
                    roles_by_user.get(user.NguoiDungId, [])
                ),
                "vaiTroIds": role_ids_by_user.get(user.NguoiDungId, []),
                "maHocVien": db.query(LeadConversion.MaHocVien)
                .filter(
                    LeadConversion.NguoiDungId == user.NguoiDungId
                )
                .scalar(),
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
# =========================================================
# IMPORT EXCEL NGƯỜI DÙNG
# =========================================================
# =========================================================


# =========================================================
# PREVIEW IMPORT EXCEL
#
# POST /users/import/preview
#
# Chức năng:
# - Upload file Excel
# - KHÔNG ghi dữ liệu vào database
# - Kiểm tra từng dòng
# - Kiểm tra họ tên
# - Kiểm tra email
# - Kiểm tra email trùng database
# - Kiểm tra email trùng trong chính file
# - Kiểm tra vai trò
# - Xác định dòng hợp lệ / lỗi
# =========================================================
@router.get(
    "/import/template",
    dependencies=[
        Depends(require_permission("USER_CREATE"))
    ],
)
def download_user_import_template():
    template_path = (
        Path(__file__).resolve().parent.parent
        / "templates"
        / "user_import_template.xlsx"
    )

    if not template_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy file Excel mẫu.",
        )

    return FileResponse(
        path=template_path,
        filename="user_import_template.xlsx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
@router.post(
    "/import/preview",
    dependencies=[
        Depends(
            require_permission("USER_CREATE")
        )
    ],
)
def preview_import_users(
    file: UploadFile = File(
        ...,
        description=(
            "File Excel (.xlsx) danh sách "
            "người dùng cần kiểm tra"
        ),
    ),
    db: Session = Depends(get_db),
):
    """
    Preview file Excel.

    Endpoint này CHỈ kiểm tra dữ liệu.
    Không tạo tài khoản.
    Không gửi email.
    Không thay đổi database.
    """

    # -----------------------------------------------------
    # Kiểm tra tên file cơ bản
    # -----------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng chọn file Excel.",
        )

    filename = file.filename.lower()

    if not filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Chỉ hỗ trợ file Excel định dạng .xlsx."
            ),
        )

    # -----------------------------------------------------
    # Gọi service xử lý preview
    # -----------------------------------------------------

    return preview_user_import(
        db=db,
        file=file,
    )


# =========================================================
# IMPORT EXCEL
#
# POST /users/import
#
# Chức năng:
# - Đọc file Excel
# - Kiểm tra từng dòng
# - Bỏ qua dòng lỗi
# - Chỉ tạo tài khoản hợp lệ
# - Kiểm tra email trùng
# - Kiểm tra vai trò
# - Sinh mật khẩu tạm thời
# - Hash mật khẩu
# - Gán vai trò
# - Bắt buộc đổi mật khẩu
# - Gửi email mật khẩu tạm thời
# - Trả về thống kê
# =========================================================

@router.post(
    "/import",
    status_code=201,
    dependencies=[
        Depends(
            require_permission("USER_CREATE")
        )
    ],
)
def import_users(
    file: UploadFile = File(
        ...,
        description=(
            "File Excel (.xlsx) danh sách "
            "người dùng cần import"
        ),
    ),
    db: Session = Depends(get_db),
):
    """
    Import người dùng từ Excel.

    Dòng hợp lệ:
        -> tạo tài khoản
        -> gán vai trò
        -> sinh mật khẩu tạm thời
        -> gửi email

    Dòng lỗi:
        -> bỏ qua
        -> không làm dừng toàn bộ quá trình
    """

    # -----------------------------------------------------
    # Kiểm tra file
    # -----------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng chọn file Excel.",
        )

    filename = file.filename.lower()

    if not filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Chỉ hỗ trợ file Excel định dạng .xlsx."
            ),
        )

    # -----------------------------------------------------
    # Gọi service import
    # -----------------------------------------------------

    return import_valid_users(
        db=db,
        file=file,
    )


# =========================================================
# ADMIN TẠO TÀI KHOẢN THỦ CÔNG
#
# POST /users/create-account
#
# Admin chỉ nhập:
# - Họ tên
# - Email
# - Vai trò
#
# Backend:
# - Kiểm tra email
# - Sinh mật khẩu tạm thời
# - Hash mật khẩu
# - Gán vai trò
# - Bắt buộc đổi mật khẩu
# - Gửi email
# =========================================================

@router.post(
    "/create-account",
    status_code=201,
    dependencies=[
        Depends(
            require_permission("USER_CREATE")
        )
    ],
)
def admin_create_user_endpoint(
    request: AdminCreateUserRequest,
    db: Session = Depends(get_db),
):
    return admin_create_user(
        db,
        request,
    )


# =========================================================
# TẠO NGƯỜI DÙNG API CŨ
#
# POST /users/
#
# Giữ nguyên để không ảnh hưởng chức năng hiện tại.
# =========================================================

@router.post(
    "/",
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
#
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
#
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
#
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


# =========================================================
# XÓA NGƯỜI DÙNG
#
# DELETE /users/{nguoi_dung_id}
# =========================================================

@router.delete(
    "/{nguoi_dung_id}",
    status_code=200,
    dependencies=[
        Depends(
            require_permission("USER_DELETE")
        )
    ],
)
def delete_user_endpoint(
    nguoi_dung_id: int,
    current_user: NguoiDung = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    # -----------------------------------------------------
    # Không cho phép tự xóa tài khoản
    # -----------------------------------------------------

    if (
        current_user.NguoiDungId
        == nguoi_dung_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Không thể xóa tài khoản "
                "đang đăng nhập"
            ),
        )

    return delete_user(
        db,
        nguoi_dung_id,
    )