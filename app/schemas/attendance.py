from pydantic import BaseModel, ConfigDict, Field, field_validator


class AbsenceRequestWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schedule_id: int = Field(alias="scheduleId", gt=0)
    reason: str = Field(alias="reason", min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value:
            raise ValueError("Vui lòng nhập lý do xin nghỉ.")
        return value


class AbsenceRequestDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    decision: str = Field(pattern="^(approved|rejected)$")
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value:
            raise ValueError("Vui lòng nhập lý do duyệt hoặc từ chối.")
        return value
