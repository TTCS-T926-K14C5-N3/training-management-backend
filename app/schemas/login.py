from pydantic import BaseModel, EmailStr, Field


# Cấu trúc dữ liệu Frontend gửi lên khi đăng nhập
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=6,
        max_length=100
    )

    # Token kích hoạt lấy từ link trong email tạo tài khoản.
    # Có token này thì tài khoản được kích hoạt ngay
    # trong lần đăng nhập đầu tiên.
    activation_token: str | None = Field(
        default=None,
        max_length=255
    )


# Cấu trúc dữ liệu Backend trả về chứa Token
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"