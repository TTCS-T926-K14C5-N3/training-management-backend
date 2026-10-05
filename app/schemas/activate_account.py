from pydantic import BaseModel, Field


class ActivateAccountRequest(BaseModel):
    token: str = Field(
        min_length=1,
        description="Token kích hoạt tài khoản"
    )