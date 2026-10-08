import re
from datetime import date

from pydantic import BaseModel, Field, field_validator


class UpdateProfileRequest(BaseModel):
    ho_ten: str = Field(
        min_length=1,
        max_length=100,
        description="Họ và tên"
    )

    so_dien_thoai: str | None = Field(
        default=None,
        max_length=20,
        description="Số điện thoại Việt Nam"
    )

    ngay_sinh: date | None = Field(
        default=None,
        description="Ngày sinh"
    )

    dia_chi: str | None = Field(
        default=None,
        max_length=255,
        description="Địa chỉ"
    )

    @field_validator("ho_ten")
    @classmethod
    def validate_ho_ten(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Họ tên không được để trống")

        return value

    @field_validator("so_dien_thoai")
    @classmethod
    def validate_so_dien_thoai(
        cls,
        value: str | None
    ) -> str | None:
        if value is None or value.strip() == "":
            return None

        value = value.strip()

        # Số điện thoại Việt Nam:
        # 03xxxxxxxx
        # 05xxxxxxxx
        # 07xxxxxxxx
        # 08xxxxxxxx
        # 09xxxxxxxx
        # hoặc dạng +84xxxxxxxxx
        pattern = r"^(0|\+84)(3|5|7|8|9)[0-9]{8}$"

        if not re.fullmatch(pattern, value):
            raise ValueError(
                "Số điện thoại Việt Nam không hợp lệ"
            )

        return value

    @field_validator("dia_chi")
    @classmethod
    def validate_dia_chi(
        cls,
        value: str | None
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None
    