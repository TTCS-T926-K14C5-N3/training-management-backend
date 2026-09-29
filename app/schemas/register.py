from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    ho_ten: str = Field(
        min_length=2,
        max_length=100
    )

    email: EmailStr

    so_dien_thoai: str | None = Field(
        default=None,
        max_length=20
    )

    password: str = Field(
        min_length=6,
        max_length=100
    )