from datetime import date
from decimal import Decimal
import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.services.business_time import business_now


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


class StudentProfileWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ho_ten: str = Field(alias="hoTen", min_length=1, max_length=100)
    email: EmailStr
    so_dien_thoai: str | None = Field(
        default=None,
        alias="soDienThoai",
        max_length=20,
    )
    ngay_sinh: date | None = Field(default=None, alias="ngaySinh")
    dia_chi: str | None = Field(default=None, alias="diaChi", max_length=255)
    trinh_do_dau_vao: str | None = Field(
        default=None,
        alias="trinhDoDauVao",
        max_length=150,
    )
    ghi_chu: str | None = Field(default=None, alias="ghiChu", max_length=2000)

    @field_validator(
        "ho_ten",
        "so_dien_thoai",
        "dia_chi",
        "trinh_do_dau_vao",
        "ghi_chu",
        mode="before",
    )
    @classmethod
    def normalize_profile_text(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("ho_ten")
    @classmethod
    def validate_student_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Họ tên không được để trống.")
        return value

    @field_validator("so_dien_thoai")
    @classmethod
    def validate_student_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"^(0|\+84)(3|5|7|8|9)[0-9]{8}$", value):
            raise ValueError("Số điện thoại Việt Nam không hợp lệ.")
        return value

class SubjectCreate(BaseModel):
    ma_mon_hoc: str = Field(alias="maMonHoc", min_length=1, max_length=30)
    ten_mon_hoc: str = Field(alias="tenMonHoc", min_length=1, max_length=150)
    so_tin_chi: int | None = Field(default=None, alias="soTinChi", ge=1, le=30)
    so_buoi: int = Field(default=1, alias="soBuoi", gt=0)
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


class ClassInstructorAssignment(BaseModel):
    mon_hoc_id: int = Field(alias="monHocId", gt=0)
    giang_vien_id: int = Field(alias="giangVienId", gt=0)
    vai_tro: Literal["Chính", "Trợ giảng"] = Field(alias="vaiTro")


class StudentEnrollmentActionWrite(BaseModel):
    model_config = {"populate_by_name": True}

    loai_thao_tac: Literal["BaoLuu", "ChuyenLop", "ThoiHoc"] = Field(
        alias="loaiThaoTac"
    )
    ngay_hieu_luc: date = Field(alias="ngayHieuLuc")
    ly_do: str = Field(alias="lyDo", min_length=1, max_length=1000)
    lop_hoc_dich_id: int | None = Field(
        default=None,
        alias="lopHocDichId",
        gt=0,
    )

    @field_validator("ly_do", mode="before")
    @classmethod
    def normalize_action_reason(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("ly_do")
    @classmethod
    def validate_action_reason(cls, value: str) -> str:
        if not value:
            raise ValueError("Vui lòng nhập lý do xử lý học viên.")
        return value

    @model_validator(mode="after")
    def validate_transfer_target(self):
        if (self.loai_thao_tac == "ChuyenLop") != (
            self.lop_hoc_dich_id is not None
        ):
            raise ValueError(
                "Chỉ thao tác chuyển lớp mới được chọn lớp đích."
            )
        return self


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
    ngay_khai_giang: date = Field(
        default_factory=lambda: business_now().date(),
        alias="ngayKhaiGiang",
    )
    si_so_toi_da: int = Field(default=30, alias="siSoToiDa", gt=0, le=500)
    hinh_thuc: Literal["Trực tiếp", "Trực tuyến", "Kết hợp"] = Field(
        default="Trực tiếp",
        alias="hinhThuc",
    )
    phong_hoc_id: int | None = Field(default=None, alias="phongHocId", gt=0)
    link_truc_tuyen: str | None = Field(
        default=None,
        alias="linkTrucTuyen",
        max_length=500,
    )
    tien_do: Decimal = Field(
        default=Decimal("0"),
        alias="tienDo",
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
    )
    trang_thai: Literal[
        "Chuẩn bị",
        "Đang học",
        "Kết thúc",
        "Hủy",
        "Đang hoạt động",
    ] = Field(default="Chuẩn bị", alias="trangThai")
    phan_cong_giang_vien: list[ClassInstructorAssignment] | None = Field(
        default=None,
        alias="phanCongGiangVien",
    )

    @field_validator("hoc_vien_ids", "mon_hoc_ids")
    @classmethod
    def validate_unique_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value) or len(value) != len(set(value)):
            raise ValueError("Danh sách mã không hợp lệ hoặc bị trùng.")
        return value

    @field_validator("link_truc_tuyen", mode="before")
    @classmethod
    def normalize_online_link(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value


class RoomWrite(BaseModel):
    ma_phong: str = Field(alias="maPhong", min_length=1, max_length=30)
    ten_phong: str = Field(alias="tenPhong", min_length=1, max_length=100)
    suc_chua: int = Field(alias="sucChua", gt=0, le=1000)
    loai_phong: Literal["Trực tiếp", "Trực tuyến"] = Field(
        default="Trực tiếp",
        alias="loaiPhong",
    )

    @field_validator("ma_phong", "ten_phong", mode="before")
    @classmethod
    def strip_room_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class ClassEnrollmentWrite(BaseModel):
    hoc_vien_ids: list[int] = Field(alias="hocVienIds", min_length=1)

    @field_validator("hoc_vien_ids")
    @classmethod
    def validate_student_ids(cls, value: list[int]) -> list[int]:
        if any(item <= 0 for item in value):
            raise ValueError("Mã học viên không hợp lệ.")
        return value


RoomCreate = RoomWrite
ClassEnrollmentsWrite = ClassEnrollmentWrite
StudentProfileUpdate = StudentProfileWrite


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
