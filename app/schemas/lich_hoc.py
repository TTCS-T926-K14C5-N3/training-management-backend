from datetime import date, time
from typing import Annotated, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.services import business_time


class LichHocWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lop_hoc_id: int = Field(alias="lopHocId", gt=0)
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
    bai_hoc_id: int | None = Field(default=None, alias="baiHocId", gt=0)
    ngay_hoc: date = Field(alias="ngayHoc")
    gio_bat_dau: time = Field(alias="gioBatDau")
    gio_ket_thuc: time = Field(alias="gioKetThuc")
    phong_hoc_id: int = Field(alias="phongHocId", gt=0)
    giang_vien_id: int = Field(alias="giangVienId", gt=0)
    xac_nhan_trung_lich: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "xacNhanTrungLich",
            "ghiDeXungDot",
        ),
    )
    ly_do_ghi_de: str | None = Field(
        default=None,
        alias="lyDoGhiDe",
        max_length=1000,
    )

    @field_validator("gio_bat_dau", "gio_ket_thuc")
    @classmethod
    def validate_local_time(cls, value: time) -> time:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError(
                "Giờ học phải dùng giờ địa phương, không kèm múi giờ."
            )
        return value

    @field_validator("ly_do_ghi_de", mode="before")
    @classmethod
    def normalize_override_reason(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.gio_ket_thuc <= self.gio_bat_dau:
            raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
        if self.xac_nhan_trung_lich and len(self.ly_do_ghi_de or "") < 5:
            raise ValueError(
                "Lý do xác nhận ghi đè phải có ít nhất 5 ký tự."
            )
        now = business_time.business_now()
        if self.ngay_hoc < now.date():
            raise ValueError("Ngày học không được nằm trong quá khứ.")
        if self.ngay_hoc == now.date():
            current_time = now.timetz().replace(tzinfo=None)
            if self.gio_ket_thuc <= current_time:
                raise ValueError(
                    "Buổi học phải kết thúc sau thời điểm hiện tại."
                )
            if self.gio_bat_dau <= current_time:
                raise ValueError(
                    "Buổi học phải bắt đầu sau thời điểm hiện tại."
                )
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


class DiemDanhEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    hoc_vien_id: int = Field(alias="hocVienId", gt=0)
    trang_thai: Literal[
        "Có mặt",
        "Đi muộn",
        "Vắng có phép",
        "Vắng không phép",
    ] = Field(alias="trangThai")
    ghi_chu: str | None = Field(default=None, alias="ghiChu", max_length=1000)

    @field_validator("ghi_chu", mode="before")
    @classmethod
    def normalize_attendance_note(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        return value


class DiemDanhWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    hoc_viens: list[DiemDanhEntry] = Field(alias="hocViens", min_length=1)
    ly_do: str | None = Field(
        default=None,
        alias="lyDo",
        min_length=5,
        max_length=1000,
    )

    @field_validator("ly_do", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("hoc_viens")
    @classmethod
    def validate_unique_students(
        cls,
        value: list[DiemDanhEntry],
    ) -> list[DiemDanhEntry]:
        student_ids = [item.hoc_vien_id for item in value]
        if len(student_ids) != len(set(student_ids)):
            raise ValueError("Danh sách điểm danh không được trùng học viên.")
        return value


class LichHocRepeatWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lop_hoc_id: int = Field(alias="lopHocId", gt=0)
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
    ngay_bat_dau: date = Field(alias="ngayBatDau")
    so_buoi: int = Field(alias="soBuoi", ge=1, le=60)
    thu_trong_tuan: list[int] = Field(alias="thuTrongTuan", min_length=1)
    ngay_nghi: list[date] = Field(default_factory=list, alias="ngayNghi")
    gio_bat_dau: time = Field(alias="gioBatDau")
    gio_ket_thuc: time = Field(alias="gioKetThuc")
    phong_hoc_id: int = Field(alias="phongHocId", gt=0)
    giang_vien_id: int = Field(alias="giangVienId", gt=0)
    ghi_de_xung_dot: bool = Field(default=False, alias="ghiDeXungDot")
    ly_do_ghi_de: str | None = Field(default=None, alias="lyDoGhiDe", max_length=1000)

    @field_validator("thu_trong_tuan")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 1 or day > 7 for day in value):
            raise ValueError("Thứ trong tuần phải nằm trong khoảng từ 1 đến 7.")
        if len(value) != len(set(value)):
            raise ValueError("Thứ trong tuần không được trùng lặp.")
        return value

    @field_validator("gio_bat_dau", "gio_ket_thuc")
    @classmethod
    def validate_local_time(cls, value: time) -> time:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("Giờ học phải dùng giờ địa phương, không kèm múi giờ.")
        return value

    @field_validator("ly_do_ghi_de", mode="before")
    @classmethod
    def normalize_override_reason(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def validate_time_and_override(self):
        if self.gio_ket_thuc <= self.gio_bat_dau:
            raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
        if self.ghi_de_xung_dot and len(self.ly_do_ghi_de or "") < 5:
            raise ValueError("Lý do xác nhận ghi đè phải có ít nhất 5 ký tự.")
        if self.ngay_bat_dau < business_time.business_now().date():
            raise ValueError("Ngày bắt đầu không được nằm trong quá khứ.")
        return self
