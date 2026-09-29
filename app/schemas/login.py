from pydantic import BaseModel

# Cấu trúc dữ liệu Frontend gửi lên khi đăng nhập
class LoginRequest(BaseModel):
    email: str
    password: str

# Cấu trúc dữ liệu Backend trả về chứa Token
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"