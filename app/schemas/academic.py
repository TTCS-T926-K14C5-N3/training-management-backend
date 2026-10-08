from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class TrainingProgramWrite(BaseModel):
    ma_chuong_trinh: str = Field(alias="maChuongTrinh", min_length=1, max_length=30)
    ten_chuong_trinh: str = Field(
        alias="tenChuongTrinh",
        min_length=1,
        max_length=150,
    )
    mo_ta: str | None = Field(default=None, alias="moTa", max_length=1000)
    tong_thoi_luong: int = Field(alias="tongThoiLuong", gt=0)
    hoc_phi_chuan: Decimal = Field(
        alias="hocPhiChuan",
        ge=0,
        max_digits=12,
        decimal_places=2,
    )
    trang_thai: str = Field(default="Đang áp dụng", alias="trangThai")

    @field_validator("ma_chuong_trinh", "ten_chuong_trinh", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("mo_ta", mode="before")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("trang_thai")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"Đang áp dụng", "Ngừng áp dụng"}:
            raise ValueError("Trạng thái chương trình không hợp lệ.")
        return value


class SubjectCreate(BaseModel):
    ma_mon_hoc: str = Field(alias="maMonHoc", min_length=1, max_length=30)
    ten_mon_hoc: str = Field(alias="tenMonHoc", min_length=1, max_length=150)
    so_tin_chi: int | None = Field(default=None, alias="soTinChi", ge=1, le=30)
    so_buoi: int = Field(default=1, alias="soBuoi", ge=1)
    trong_so: Decimal = Field(
        default=Decimal("1"),
        alias="trongSo",
        ge=0,
        le=1,
        max_digits=5,
        decimal_places=2,
    )
    mo_ta_chuan_dau_ra: str | None = Field(
        default=None,
        alias="moTaChuanDauRa",
        max_length=1000,
    )
    trang_thai: str = Field(default="Đang hoạt động", alias="trangThai")

    @field_validator("ma_mon_hoc", "ten_mon_hoc", mode="before")
    @classmethod
    def strip_subject_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("mo_ta_chuan_dau_ra", mode="before")
    @classmethod
    def normalize_subject_description(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("trang_thai")
    @classmethod
    def validate_subject_status(cls, value: str) -> str:
        if value not in {"Đang hoạt động", "Ngừng hoạt động"}:
            raise ValueError("Trạng thái môn học không hợp lệ.")
        return value


class SubjectUpdate(SubjectCreate):
    pass


class ClassWrite(BaseModel):
    ma_lop: str = Field(alias="maLop", min_length=1, max_length=30)
    ten_lop: str = Field(alias="tenLop", min_length=1, max_length=150)
    nam_hoc: str = Field(alias="namHoc", min_length=9, max_length=9)
    chuong_trinh_id: int | None = Field(
        default=None,
        alias="chuongTrinhId",
        gt=0,
    )
    giang_vien_id: int | None = Field(default=None, alias="giangVienId", gt=0)
    hoc_vien_ids: list[int] = Field(default_factory=list, alias="hocVienIds")
    mon_hoc_ids: list[int] = Field(default_factory=list, alias="monHocIds")


class GradeWrite(BaseModel):
    lop_hoc_id: int = Field(alias="lopHocId", gt=0)
    hoc_vien_id: int = Field(alias="hocVienId", gt=0)
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
    hoc_ky: int = Field(alias="hocKy", ge=1, le=3)
    nam_hoc: str = Field(alias="namHoc", min_length=9, max_length=9)
    diem_qua_trinh: Decimal | None = Field(
        default=None,
        alias="diemQuaTrinh",
        ge=0,
        le=10,
        max_digits=4,
        decimal_places=2,
    )
    diem_giua_ky: Decimal | None = Field(
        default=None,
        alias="diemGiuaKy",
        ge=0,
        le=10,
        max_digits=4,
        decimal_places=2,
    )
    diem_cuoi_ky: Decimal | None = Field(
        default=None,
        alias="diemCuoiKy",
        ge=0,
        le=10,
        max_digits=4,
        decimal_places=2,
    )
