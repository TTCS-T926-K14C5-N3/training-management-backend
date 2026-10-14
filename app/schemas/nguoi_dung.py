from pydantic import BaseModel, EmailStr, Field
from pydantic import BaseModel, Field, validator
from typing import List, Optional

# ============================================================
# TẠO NGƯỜI DÙNG
# ============================================================

class NguoiDungCreate(BaseModel):
    ho_ten: str = Field(
        min_length=1,
        max_length=100
    )

    email: EmailStr

    so_dien_thoai: str | None = Field(
        default=None,
        max_length=20
    )

    password: str = Field(
        min_length=8
    )


# ============================================================
# CẬP NHẬT NGƯỜI DÙNG
# ============================================================

class NguoiDungUpdate(BaseModel):
    ho_ten: str | None = Field(
        default=None,
        min_length=1,
        max_length=100
    )

    email: EmailStr | None = None

    so_dien_thoai: str | None = Field(
        default=None,
        max_length=20
    )

    trang_thai: str | None = Field(
        default=None,
        max_length=50
    )


# ============================================================
# KHÓA TÀI KHOẢN
# ============================================================
class NguoiDungLock(BaseModel):
    ly_do_khoa: str = Field(..., min_length=1, description="Lý do khóa tài khoản")

    @validator('ly_do_khoa')
    def validate_ly_do_khoa(cls, v):
        if not v or not v.strip():
            raise ValueError('Lý do khóa tài khoản không được để trống')
        return v.strip()
    # ============================================================
# GÁN VAI TRÒ CHO NGƯỜI DÙNG
# ============================================================

class GanVaiTroRequest(BaseModel):
    vai_tro_id: int = Field(..., description="ID của vai trò cần gán cho người dùng")
    # ============================================================
# BÁO CÁO KẾT QUẢ NHẬP DỮ LIỆU (SCRUM-138)
# ============================================================

class ChiTietLoiNhap(BaseModel):
    dong: int
    noi_dung_loi: str

class BaoCaoKetQuaNhapResponse(BaseModel):
    tong_so_luong: int
    so_luong_thanh_cong: int
    so_luong_that_bai: int
    danh_sach_loi: Optional[List[ChiTietLoiNhap]] = []
    # ============================================================
# CẬP NHẬT HỒ SƠ CÁ NHÂN (SCRUM-148)
# ============================================================

class CapNhatHoSoCaNhanRequest(BaseModel):
    ho_ten: Optional[str] = None
    so_dien_thoai: Optional[str] = None