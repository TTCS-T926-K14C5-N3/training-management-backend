from decimal import Decimal

from pydantic import BaseModel, Field


class SubjectCreate(BaseModel):
    ma_mon_hoc: str = Field(alias="maMonHoc", min_length=1, max_length=30)
    ten_mon_hoc: str = Field(alias="tenMonHoc", min_length=1, max_length=150)
    so_tin_chi: int | None = Field(default=None, alias="soTinChi", ge=1, le=30)


class SubjectUpdate(SubjectCreate):
    pass


class ClassWrite(BaseModel):
    ma_lop: str = Field(alias="maLop", min_length=1, max_length=30)
    ten_lop: str = Field(alias="tenLop", min_length=1, max_length=100)
    nam_hoc: str = Field(alias="namHoc", min_length=9, max_length=9)
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
