from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class LeadWrite(BaseModel):
    ho_ten: str = Field(alias="hoTen", min_length=1, max_length=100)
    so_dien_thoai: str = Field(alias="soDienThoai", min_length=8, max_length=30)
    email: EmailStr | None = None
    nguon: str = Field(min_length=1, max_length=100)
    chuong_trinh_id: int | None = Field(default=None, alias="chuongTrinhId", gt=0)
    trang_thai: str = Field(default="Mới", alias="trangThai", max_length=30)
    ghi_chu: str | None = Field(default=None, alias="ghiChu", max_length=1000)
    ly_do_tu_choi: str | None = Field(
        default=None,
        alias="lyDoTuChoi",
        max_length=500,
    )

    @field_validator("ho_ten", "so_dien_thoai", "nguon", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("ghi_chu", "ly_do_tu_choi", mode="before")
    @classmethod
    def strip_optional_text(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class PublicLeadWrite(BaseModel):
    ho_ten: str = Field(alias="hoTen", min_length=1, max_length=100)
    so_dien_thoai: str = Field(alias="soDienThoai", min_length=8, max_length=30)
    email: EmailStr | None = None
    chuong_trinh_id: int | None = Field(default=None, alias="chuongTrinhId", gt=0)
    nguon: str = Field(default="Website", min_length=1, max_length=100)
    website: str = Field(default="", max_length=255)

    @field_validator("ho_ten", "so_dien_thoai", "nguon", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class LeadAssignmentWrite(BaseModel):
    consultant_ids: list[int] = Field(alias="consultantIds", max_length=20)


class LeadBulkAssignmentWrite(LeadAssignmentWrite):
    lead_ids: list[int] = Field(alias="leadIds", min_length=1, max_length=100)


class LeadStatusWrite(BaseModel):
    trang_thai: str = Field(alias="trangThai", min_length=1, max_length=30)
    ly_do_tu_choi: str | None = Field(
        default=None,
        alias="lyDoTuChoi",
        max_length=500,
    )


class LeadInteractionWrite(BaseModel):
    loai: str = Field(min_length=1, max_length=20)
    noi_dung: str = Field(alias="noiDung", min_length=1, max_length=2000)
    thoi_diem: datetime = Field(alias="thoiDiem")
    hen_goi_lai_luc: datetime | None = Field(default=None, alias="henGoiLaiLuc")

    @field_validator("noi_dung", mode="before")
    @classmethod
    def strip_content(cls, value):
        return value.strip() if isinstance(value, str) else value
