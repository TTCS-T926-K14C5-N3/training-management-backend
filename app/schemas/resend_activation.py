from pydantic import BaseModel, EmailStr


class ResendActivationRequest(BaseModel):
    email: EmailStr
