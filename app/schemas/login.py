from pydantic import BaseModel, EmailStr, Field


# Cấu trúc dữ liệu Frontend gửi lên khi đăng nhập
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=6,
        max_length=100
    )


# Cấu trúc dữ liệu Backend trả về chứa Token
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"