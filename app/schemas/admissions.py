from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field, field_validator


LEAD_STATUSES = {
    "Mới",
    "Đã liên hệ",
    "Đang tư vấn",
    "Hẹn học thử",
    "Chốt",
    "Từ chối",
    "Đang liên hệ",
    "Tiềm năng",
    "Đã chuyển đổi",
    "Đã nhập học",
    "Không tiềm năng",
}


class PublicLeadCreate(BaseModel):
    ho_ten: str = Field(alias="hoTen", min_length=1, max_length=100)
    so_dien_thoai: str = Field(alias="soDienThoai", min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    chuong_trinh_id: int = Field(alias="chuongTrinhId", gt=0)
    nguon: str = Field(default="Website", alias="nguon", min_length=1, max_length=100)
    website: str | None = Field(default=None, max_length=255)

    @field_validator("ho_ten", "so_dien_thoai", "nguon", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip().lower() or None
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and (value.count("@") != 1 or "." not in value.rsplit("@", 1)[-1]):
            raise ValueError("Địa chỉ email không hợp lệ.")
        return value


class LeadWrite(BaseModel):
    ho_ten: str = Field(alias="hoTen", min_length=1, max_length=100)
    so_dien_thoai: str = Field(alias="soDienThoai", min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    chuong_trinh_id: int | None = Field(
        default=None,
        alias="chuongTrinhId",
        gt=0,
    )
    nguon: str = Field(alias="nguon", min_length=1, max_length=100)
    ghi_chu: str | None = Field(default=None, alias="ghiChu", max_length=1000)
    ly_do_tu_choi: str | None = Field(
        default=None,
        alias="lyDoTuChoi",
        max_length=500,
    )
    trang_thai: str = Field(default="Mới", alias="trangThai")

    @field_validator("ho_ten", "so_dien_thoai", "nguon", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return value.strip().lower() or None if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and (value.count("@") != 1 or "." not in value.rsplit("@", 1)[-1]):
            raise ValueError("Địa chỉ email không hợp lệ.")
        return value

    @field_validator("trang_thai")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in LEAD_STATUSES:
            raise ValueError("Trạng thái khách hàng tiềm năng không hợp lệ.")
        return value

    @field_validator("ghi_chu", mode="before")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("ly_do_tu_choi", mode="before")
    @classmethod
    def normalize_decline_reason(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("ly_do_tu_choi")
    @classmethod
    def require_decline_reason(cls, value: str | None, info) -> str | None:
        if info.data.get("trang_thai") == "Từ chối" and not value:
            raise ValueError("Vui lòng chọn hoặc nhập lý do từ chối.")
        return value


class LeadInteractionWrite(BaseModel):
    loai: str = Field(alias="loai")
    noi_dung: str = Field(alias="noiDung", min_length=1, max_length=2000)
    thoi_diem: datetime | None = Field(default=None, alias="thoiDiem")
    hen_goi_lai_luc: datetime | None = Field(default=None, alias="henGoiLaiLuc")

    @field_validator("loai")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in {"Gọi", "Nhắn tin", "Gặp"}:
            raise ValueError("Loại tương tác không hợp lệ.")
        return value

    @field_validator("noi_dung", mode="before")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("hen_goi_lai_luc")
    @classmethod
    def validate_follow_up(cls, value: datetime | None, info) -> datetime | None:
        happened_at = info.data.get("thoi_diem")
        if value is not None and happened_at is not None and value < happened_at:
            raise ValueError("Thời điểm gọi lại phải sau thời điểm tương tác.")
        return value


class LeadStatusWrite(BaseModel):
    trang_thai: str = Field(alias="trangThai")
    ly_do_tu_choi: str | None = Field(default=None, alias="lyDoTuChoi", max_length=500)

    @field_validator("trang_thai")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in LEAD_STATUSES:
            raise ValueError("Trạng thái khách hàng tiềm năng không hợp lệ.")
        return value

    @field_validator("ly_do_tu_choi", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("ly_do_tu_choi")
    @classmethod
    def require_reason(cls, value: str | None, info) -> str | None:
        if info.data.get("trang_thai") == "Từ chối" and not value:
            raise ValueError("Vui lòng chọn hoặc nhập lý do từ chối.")
        return value


class LeadAssignmentsWrite(BaseModel):
    assigned_user_ids: list[int] = Field(
        alias="consultantIds",
        validation_alias=AliasChoices("consultantIds", "assignedUserIds"),
    )

    @field_validator("assigned_user_ids")
    @classmethod
    def validate_unique_users(cls, value: list[int]) -> list[int]:
        if any(user_id <= 0 for user_id in value) or len(value) != len(set(value)):
            raise ValueError("Danh sách tư vấn viên không hợp lệ hoặc bị trùng.")
        if len(value) > 1:
            raise ValueError("Mỗi lead chỉ được phân công cho một tư vấn viên.")
        return value


class BulkLeadAssignmentsWrite(BaseModel):
    lead_ids: list[int] = Field(
        alias="leadIds",
        validation_alias=AliasChoices("leadIds", "lead_ids"),
    )
    consultant_ids: list[int] = Field(
        alias="consultantIds",
        validation_alias=AliasChoices("consultantIds", "assignedUserIds", "consultant_ids"),
    )

    @field_validator("lead_ids")
    @classmethod
    def validate_unique_leads(cls, value: list[int]) -> list[int]:
        if not value or any(lead_id <= 0 for lead_id in value) or len(value) != len(set(value)):
            raise ValueError("Danh sách khách hàng tiềm năng không hợp lệ hoặc bị trùng.")
        return value

    @field_validator("consultant_ids")
    @classmethod
    def validate_unique_consultants(cls, value: list[int]) -> list[int]:
        if any(user_id <= 0 for user_id in value) or len(value) != len(set(value)):
            raise ValueError("Danh sách tư vấn viên không hợp lệ hoặc bị trùng.")
        if len(value) > 1:
            raise ValueError("Mỗi lead chỉ được phân công cho một tư vấn viên.")
        return value
