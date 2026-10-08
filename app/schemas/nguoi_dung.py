import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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

    @field_validator("email")
    @classmethod
    def validate_email_domain(cls, value: EmailStr | None) -> EmailStr | None:
        if value is None:
            return None

        top_level_domain = str(value).rsplit(".", maxsplit=1)[-1]
        if len(top_level_domain) < 2:
            raise ValueError("Email không đúng định dạng")

        return value

    @field_validator("so_dien_thoai")
    @classmethod
    def validate_so_dien_thoai(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None or value.strip() == "":
            return None

        value = value.strip()
        pattern = r"^(0|\+84)(3|5|7|8|9)[0-9]{8}$"

        if not re.fullmatch(pattern, value):
            raise ValueError(
                "Số điện thoại Việt Nam không hợp lệ"
            )

        return value


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
    id: int
    ho_ten: str
    email: EmailStr
    so_dien_thoai: str | None = None
    trang_thai: str | None = None
    avatar_url: str | None = None
    
    # 2 trường quan trọng cho task SCRUM-91
    role: str | None = Field(default="STUDENT", description="Vai trò của người dùng (ADMIN, TRAINER, STUDENT,...)")
    permissions: list[str] = Field(default=[], description="Danh sách quyền hạn của người dùng")

    class Config:
        from_attributes = True  # Giúp Pydantic tự chuyển đổi dữ liệu từ ORM model (SQLAlchemy)