from pydantic import (
    BaseModel,
    Field,
    model_validator,
    field_validator,
)


class ResetPasswordRequest(BaseModel):
    token: str = Field(
        min_length=20,
        max_length=255,
    )

    new_password: str = Field(
        min_length=8,
        max_length=100
    )

    confirm_password: str = Field(
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

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError(
                "Mật khẩu xác nhận không khớp"
            )

        return self