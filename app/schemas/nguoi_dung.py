import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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


class NguoiDungCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ho_ten: str = Field(alias="hoTen", min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(
        min_length=6,
        max_length=128,
        description="Mật khẩu người dùng (tối thiểu 6 ký tự)",
    )
    so_dien_thoai: str | None = Field(
        default=None,
        alias="soDienThoai",
        max_length=20,
    )

    @field_validator("so_dien_thoai")
    @classmethod
    def validate_so_dien_thoai(cls, value: str | None) -> str | None:
        return validate_phone(value)


class NguoiDungUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ho_ten: str | None = Field(
        default=None,
        alias="hoTen",
        min_length=1,
        max_length=100,
    )
    email: EmailStr | None = None
    so_dien_thoai: str | None = Field(
        default=None,
        alias="soDienThoai",
        max_length=20,
    )
    trang_thai: str | None = Field(
        default=None,
        alias="trangThai",
        max_length=50,
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
    def validate_so_dien_thoai(cls, value: str | None) -> str | None:
        return validate_phone(value)


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


class CheckPhoneResponse(BaseModel):
    phone: str
    exists: bool
    message: str
