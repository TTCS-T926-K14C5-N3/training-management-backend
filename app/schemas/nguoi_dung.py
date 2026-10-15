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

import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


# ============================================================
# VALIDATE SỐ ĐIỆN THOẠI VIỆT NAM
# ============================================================

PHONE_PATTERN = re.compile(r"^(0|\+84)(3|5|7|8|9)[0-9]{8}$")


def validate_phone(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    if not value:
        return None

    if not PHONE_PATTERN.fullmatch(value):
        raise ValueError("Số điện thoại Việt Nam không hợp lệ")

    return value


# ============================================================
# TẠO NGƯỜI DÙNG
# ============================================================

class NguoiDungCreate(BaseModel):
    ho_ten: str = Field(
        min_length=1,
        max_length=100,
    )

    email: EmailStr

    so_dien_thoai: str | None = Field(
        default=None,
        max_length=20,
    )

    @field_validator("so_dien_thoai")
    @classmethod
    def validate_so_dien_thoai(
        cls,
        value: str | None,
    ) -> str | None:
        return validate_phone(value)


# ============================================================
# CẬP NHẬT NGƯỜI DÙNG
# ============================================================

class NguoiDungUpdate(BaseModel):
    ho_ten: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    email: EmailStr | None = None

    so_dien_thoai: str | None = Field(
        default=None,
        max_length=20,
    )

    trang_thai: str | None = Field(
        default=None,
        max_length=50,
    )

    @field_validator("email")
    @classmethod
    def validate_email_domain(
        cls,
        value: EmailStr | None,
    ) -> EmailStr | None:
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
        return validate_phone(value)


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
# PHẢN HỒI THÔNG TIN NGƯỜI DÙNG (API /me)
# ============================================================

class NguoiDungResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ho_ten: str
    email: EmailStr
    so_dien_thoai: str | None = None
    trang_thai: str | None = None
    avatar_url: str | None = None

    role: str | None = Field(
        default="STUDENT",
        description="Vai trò của người dùng",
    )

    permissions: list[str] = Field(
        default_factory=list,
        description="Danh sách quyền hạn của người dùng",
    )


# ============================================================
# PHẢN HỒI KIỂM TRA SỐ ĐIỆN THOẠI TRÙNG
# ============================================================

class CheckPhoneResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    is_available: bool = Field(
        alias="isAvailable",
        description="Số điện thoại có thể sử dụng hay không",
    )

    exists: bool = Field(
        description="Số điện thoại đã tồn tại trong hệ thống hay chưa",
    )

    phone: str = Field(
        description="Số điện thoại đã kiểm tra",
    )

    message: str = Field(
        description="Thông báo kết quả kiểm tra",
    )
