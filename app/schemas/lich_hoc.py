from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LichHocWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lop_hoc_id: int = Field(alias="lopHocId", gt=0)
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
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
