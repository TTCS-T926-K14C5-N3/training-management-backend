from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LichHocWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lop_hoc_id: int = Field(alias="lopHocId", gt=0)
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
    buoi_hoc_id: int | None = Field(default=None, alias="buoiHocId", gt=0)
    ngay_hoc: date = Field(alias="ngayHoc")
    gio_bat_dau: time = Field(alias="gioBatDau")
    gio_ket_thuc: time = Field(alias="gioKetThuc")
    phong_hoc_id: int | None = Field(default=None, alias="phongHocId", gt=0)
    giang_vien_id: int = Field(alias="giangVienId", gt=0)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.gio_ket_thuc <= self.gio_bat_dau:
            raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
        return self


class LichHocGenerate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lop_hoc_id: int = Field(alias="lopHocId", gt=0)
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
    ngay_bat_dau: date = Field(alias="ngayBatDau")
    thu_trong_tuan: list[int] = Field(alias="thuTrongTuan", min_length=1, max_length=7)
    so_buoi: int = Field(alias="soBuoi", ge=1, le=200)
    gio_bat_dau: time = Field(alias="gioBatDau")
    gio_ket_thuc: time = Field(alias="gioKetThuc")
    phong_hoc_id: int | None = Field(default=None, alias="phongHocId", gt=0)
    giang_vien_id: int = Field(alias="giangVienId", gt=0)
    ngay_nghi: list[date] = Field(default_factory=list, alias="ngayNghi", max_length=100)

    @field_validator("thu_trong_tuan")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 1 or day > 7 for day in value) or len(value) != len(set(value)):
            raise ValueError("Các ngày trong tuần phải hợp lệ và không được trùng.")
        return sorted(value)

    @field_validator("ngay_nghi")
    @classmethod
    def validate_holidays(cls, value: list[date]) -> list[date]:
        if len(value) != len(set(value)):
            raise ValueError("Ngày nghỉ không được trùng.")
        return sorted(value)

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.gio_ket_thuc <= self.gio_bat_dau:
            raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
        return self


class DiemDanhBuoiHocRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    hoc_vien_id: int = Field(alias="hocVienId", gt=0)
    trang_thai: str | None = Field(default=None, alias="trangThai")

    @field_validator("trang_thai")
    @classmethod
    def validate_attendance_status(cls, value: str | None) -> str | None:
        allowed = {
            "Có mặt",
            "Đi muộn",
            "Vắng có phép",
            "Vắng không phép",
        }
        if value is not None and value not in allowed:
            raise ValueError("Trạng thái điểm danh không hợp lệ.")
        return value


class DiemDanhBuoiHocWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    records: list[DiemDanhBuoiHocRecord] = Field(min_length=1, max_length=500)

    @field_validator("records")
    @classmethod
    def validate_unique_students(
        cls,
        value: list[DiemDanhBuoiHocRecord],
    ) -> list[DiemDanhBuoiHocRecord]:
        student_ids = [item.hoc_vien_id for item in value]
        if len(student_ids) != len(set(student_ids)):
            raise ValueError("Danh sách học viên bị trùng.")
        return value


class LichHocCancel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ly_do: str = Field(alias="lyDo", max_length=1000)

    @field_validator("ly_do", mode="before")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("ly_do")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value:
            raise ValueError("Vui lòng nhập lý do hủy buổi học.")
        return value
