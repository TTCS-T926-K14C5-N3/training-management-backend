from pydantic import BaseModel, EmailStr, Field


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

    vai_tro_id: int = Field(
        ge=1,
        le=8,
        description="ID vai trò từ 1 đến 8",
    )