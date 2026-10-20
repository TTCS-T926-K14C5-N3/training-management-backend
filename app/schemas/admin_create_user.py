import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class AdminCreateUserRequest(BaseModel):
    """
    Dữ liệu Admin nhập khi tạo tài khoản.

    Admin không nhập mật khẩu.
    Backend sẽ tự sinh mật khẩu tạm thời.
    """

    ho_ten: str = Field(
        min_length=1,
        max_length=100,
        description="Họ và tên người dùng",
    )

    email: EmailStr = Field(
        description="Email đăng nhập",
    )

    so_dien_thoai: str | None = Field(
        default=None,
        max_length=20,
        description="Số điện thoại Việt Nam",
    )

    vai_tro_id: int = Field(
        ge=1,
        le=8,
        description="ID vai trò từ 1 đến 8",
    )

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
