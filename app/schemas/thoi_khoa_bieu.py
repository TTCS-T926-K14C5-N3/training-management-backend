from datetime import date, time
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SinhThoiKhoaBieuRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lop_hoc_id: int = Field(alias="lopHocId", gt=0)
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
    giang_vien_id: int = Field(alias="giangVienId", gt=0)
    phong_hoc_id: int = Field(alias="phongHocId", gt=0)
    ngay_bat_dau: date = Field(alias="ngayBatDau")
    gio_bat_dau: time = Field(alias="gioBatDau")
    gio_ket_thuc: time = Field(alias="gioKetThuc")
    tong_so_buoi: int = Field(alias="tongSoBuoi", ge=1, le=500)
    thu_trong_tuan: list[int] = Field(alias="thuTrongTuan", min_length=1)
    danh_sach_ngay_nghi: list[date] = Field(
        default_factory=list,
        alias="danhSachNgayNghi",
    )

    @field_validator("thu_trong_tuan")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if not value or any(day < 2 or day > 8 for day in value):
            raise ValueError("Thứ trong tuần phải nằm trong khoảng từ 2 đến 8.")
        if len(value) != len(set(value)):
            raise ValueError("Thứ trong tuần không được trùng lặp.")
        return value

    @field_validator("gio_bat_dau", "gio_ket_thuc")
    @classmethod
    def validate_local_time(cls, value: time) -> time:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("Giờ học phải dùng giờ địa phương, không kèm múi giờ.")
        return value

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.gio_ket_thuc <= self.gio_bat_dau:
            raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
        return self


class BuoiHocPreviewItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stt: int
    lop_hoc_id: int = Field(alias="lopHocId")
    mon_hoc_id: int = Field(alias="monHocId")
    giang_vien_id: int = Field(alias="giangVienId")
    phong_hoc_id: int = Field(alias="phongHocId")
    ngay_hoc: date = Field(alias="ngayHoc")
    gio_bat_dau: time = Field(alias="gioBatDau")
    gio_ket_thuc: time = Field(alias="gioKetThuc")

    @field_validator("gio_bat_dau", "gio_ket_thuc")
    @classmethod
    def validate_local_time(cls, value: time) -> time:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("Giờ học phải dùng giờ địa phương, không kèm múi giờ.")
        return value

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.gio_ket_thuc <= self.gio_bat_dau:
            raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
        return self


class LuuThoiKhoaBieuRequest(BaseModel):
    danh_sach_buoi_hoc: list[BuoiHocPreviewItem] = Field(
        alias="danhSachBuoiHoc",
    )

    model_config = ConfigDict(populate_by_name=True)


class GanBaiHocRequest(BaseModel):
    bai_hoc_id: int | None = Field(default=None, alias="bai_hoc_id", gt=0)
    noi_dung_bai_hoc: str | None = Field(
        default=None,
        alias="noi_dung_bai_hoc",
        max_length=1000,
    )

    model_config = ConfigDict(populate_by_name=True)


class ThoiKhoaBieuUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ngay_hoc: date | None = Field(default=None, alias="ngayHoc")
    gio_bat_dau: time | None = Field(default=None, alias="gioBatDau")
    gio_ket_thuc: time | None = Field(default=None, alias="gioKetThuc")
    phong_hoc_id: int | None = Field(default=None, alias="phongHocId", gt=0)
    giang_vien_id: int | None = Field(default=None, alias="giangVienId", gt=0)

    @field_validator("gio_bat_dau", "gio_ket_thuc")
    @classmethod
    def validate_local_time(cls, value: time | None) -> time | None:
        if value is not None and value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("Giờ học phải dùng giờ địa phương, không kèm múi giờ.")
        return value

    @model_validator(mode="after")
    def validate_time_range(self):
        if not self.model_fields_set:
            raise ValueError("Cần cung cấp ít nhất một trường cần cập nhật.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Trường cần cập nhật không được để trống.")
        return self
