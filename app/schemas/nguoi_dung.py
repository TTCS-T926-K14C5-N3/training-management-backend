from pydantic import BaseModel, EmailStr, Field


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
    ly_do_khoa: str | None = Field(
        default=None,
        max_length=255
    )