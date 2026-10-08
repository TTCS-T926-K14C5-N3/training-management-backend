from pydantic import BaseModel, Field, field_validator, model_validator


class ProgramSubjectWrite(BaseModel):
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
    thu_tu: int = Field(alias="thuTu", gt=0)
    mon_tien_quyet_id: int | None = Field(default=None, alias="monTienQuyetId", gt=0)


class ProgramSubjectsWrite(BaseModel):
    subjects: list[ProgramSubjectWrite] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_subject_list(self):
        ids = [subject.mon_hoc_id for subject in self.subjects]
        sequences = [subject.thu_tu for subject in self.subjects]
        if len(ids) != len(set(ids)):
            raise ValueError("Mỗi môn học chỉ được gắn một lần vào chương trình.")
        if len(sequences) != len(set(sequences)):
            raise ValueError("Thứ tự môn học không được trùng lặp.")
        return self


class SessionWrite(BaseModel):
    so_thu_tu: int = Field(alias="soThuTu", gt=0)
    chu_de: str = Field(alias="chuDe", min_length=1, max_length=200)
    muc_tieu: str | None = Field(default=None, alias="mucTieu", max_length=1000)

    @field_validator("chu_de", mode="before")
    @classmethod
    def strip_topic(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("muc_tieu", mode="before")
    @classmethod
    def strip_objective(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value


class SessionsWrite(BaseModel):
    sessions: list[SessionWrite] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_session_list(self):
        sequences = [session.so_thu_tu for session in self.sessions]
        if len(sequences) != len(set(sequences)):
            raise ValueError("Thứ tự buổi học không được trùng lặp.")
        return self
