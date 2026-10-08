from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ============================================================
# TẠO NGƯỜI DÙNG
# ============================================================

class NguoiDungCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ho_ten: str = Field(
        alias="hoTen",
        min_length=1,
        max_length=100
    )

    email: EmailStr

    password: str = Field(
        min_length=6,
        max_length=128,
        description="Mật khẩu người dùng (tối thiểu 6 ký tự)"
    )

    so_dien_thoai: str | None = Field(
        default=None,
        alias="soDienThoai",
        max_length=20
    )

# ============================================================
# CẬP NHẬT NGƯỜI DÙNG
# ============================================================

class NguoiDungUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ho_ten: str | None = Field(
        default=None,
        alias="hoTen",
        min_length=1,
        max_length=100
    )

    email: EmailStr | None = None

    so_dien_thoai: str | None = Field(
        default=None,
        alias="soDienThoai",
        max_length=20
    )

    trang_thai: str | None = Field(
        default=None,
        alias="trangThai",
        max_length=50
    )


# ============================================================
# KHÓA TÀI KHOẢN
# ============================================================

class NguoiDungLock(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ly_do_khoa: str = Field(
        alias="lyDoKhoa",
        min_length=1,
        max_length=255,
    )

    @field_validator("ly_do_khoa", mode="before")
    @classmethod
    def strip_lock_reason(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


# ============================================================
# PHẢN HỒI THÔNG TIN NGƯỜI DÙNG (CHO API /me)
# ============================================================

class NguoiDungResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ho_ten: str
    email: EmailStr
    so_dien_thoai: str | None = None
    trang_thai: str | None = None
    avatar_url: str | None = None
    
    # 2 trường quan trọng cho task SCRUM-91
    role: str | None = Field(default="STUDENT", description="Vai trò của người dùng (ADMIN, TRAINER, STUDENT,...)")
    permissions: list[str] = Field(default=[], description="Danh sách quyền hạn của người dùng")