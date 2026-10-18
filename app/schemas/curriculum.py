from pydantic import BaseModel, Field, field_validator


class ProgramSubjectItem(BaseModel):
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
    thu_tu: int = Field(alias="thuTu", gt=0)
    mon_tien_quyet_id: int | None = Field(
        default=None,
        alias="monTienQuyetId",
        gt=0,
    )


class ProgramSubjectsWrite(BaseModel):
    subjects: list[ProgramSubjectItem]


class ProgramSessionItem(BaseModel):
    so_thu_tu: int = Field(alias="soThuTu", gt=0)
    chu_de: str = Field(alias="chuDe", min_length=1, max_length=200)
    muc_tieu: str | None = Field(default=None, alias="mucTieu", max_length=1000)

    @field_validator("chu_de", mode="before")
    @classmethod
    def strip_topic(cls, value):
        return value.strip() if isinstance(value, str) else value


class ProgramSessionsWrite(BaseModel):
    sessions: list[ProgramSessionItem]


class ProgramSessionsClone(BaseModel):
    source_subject_id: int = Field(alias="sourceSubjectId", gt=0)
