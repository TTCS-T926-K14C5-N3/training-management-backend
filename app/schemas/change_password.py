from pydantic import (
    BaseModel,
    Field,
    field_validator
)


class ChangePasswordRequest(BaseModel):
    current_password: str

    new_password: str = Field(
        min_length=8,
        max_length=100
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, password: str):
        if not any(char.isalpha() for char in password):
            raise ValueError(
                "Mật khẩu mới phải có ít nhất một chữ cái"
            )

        if not any(char.isdigit() for char in password):
            raise ValueError(
                "Mật khẩu mới phải có ít nhất một chữ số"
            )

        return password