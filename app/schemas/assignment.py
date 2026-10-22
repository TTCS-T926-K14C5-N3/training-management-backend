from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssignmentWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lop_hoc_id: int = Field(alias="lopHocId", gt=0)
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
    lich_hoc_id: int = Field(alias="lichHocId", gt=0)
    tieu_de: str = Field(alias="tieuDe", min_length=1, max_length=200)
    mo_ta: str = Field(alias="moTa", min_length=1, max_length=10000)
    han_nop: datetime = Field(alias="hanNop")
    diem_toi_da: Decimal = Field(alias="diemToiDa", gt=0, le=99999.99, max_digits=7, decimal_places=2)
    cho_nop_muon: bool = Field(default=False, alias="choNopMuon")
    han_nop_muon: datetime | None = Field(default=None, alias="hanNopMuon")
    loai_phat_nop_muon: str = Field(default="none", alias="loaiPhatNopMuon")
    gia_tri_phat: Decimal = Field(default=Decimal("0.00"), alias="giaTriPhat", ge=0, le=99999.99, max_digits=7, decimal_places=2)
    diem_san_toi_thieu: Decimal = Field(default=Decimal("0.00"), alias="diemSanToiThieu", ge=0, le=99999.99, max_digits=7, decimal_places=2)

    @field_validator("tieu_de", "mo_ta", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("loai_phat_nop_muon")
    @classmethod
    def validate_penalty_type(cls, value: str) -> str:
        allowed = {"none", "percentage_per_day", "fixed_percentage", "fixed_points"}
        if value not in allowed:
            raise ValueError(f"Loại phạt nộp muộn không hợp lệ. Phải thuộc: {', '.join(allowed)}")
        return value


class LatePolicyConfigWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cho_nop_muon: bool = Field(default=False, alias="choNopMuon")
    han_nop_muon: datetime | None = Field(default=None, alias="hanNopMuon")
    loai_phat_nop_muon: str = Field(default="none", alias="loaiPhatNopMuon")
    gia_tri_phat: Decimal = Field(default=Decimal("0.00"), alias="giaTriPhat", ge=0, le=99999.99, max_digits=7, decimal_places=2)
    diem_san_toi_thieu: Decimal = Field(default=Decimal("0.00"), alias="diemSanToiThieu", ge=0, le=99999.99, max_digits=7, decimal_places=2)

    @field_validator("loai_phat_nop_muon")
    @classmethod
    def validate_penalty_type(cls, value: str) -> str:
        allowed = {"none", "percentage_per_day", "fixed_percentage", "fixed_points"}
        if value not in allowed:
            raise ValueError(f"Loại phạt nộp muộn không hợp lệ. Phải thuộc: {', '.join(allowed)}")
        return value


class AssignmentGradeWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    diem: Decimal = Field(ge=0, le=99999.99, max_digits=7, decimal_places=2)
    diem_goc: Decimal | None = Field(default=None, alias="diemGoc", ge=0, le=99999.99, max_digits=7, decimal_places=2)
    nhan_xet: str | None = Field(default=None, alias="nhanXet", max_length=2000)


class ReopenWrite(BaseModel):
    ly_do: str = Field(alias="lyDo", min_length=1, max_length=1000)

    @field_validator("ly_do", mode="before")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class RepositoryUrl(BaseModel):
    url: str = Field(min_length=1, max_length=1000)

    @field_validator("url", mode="before")
    @classmethod
    def validate_repository_url(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        value = value.strip()
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not parsed.path.strip("/")
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Repository URL must be a valid HTTPS URL with a repository path.")
        return value


