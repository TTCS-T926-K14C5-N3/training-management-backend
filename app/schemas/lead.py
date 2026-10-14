from pydantic import BaseModel, Field, EmailStr
from typing import Optional


class LeadCreate(BaseModel):
    ho_ten: str = Field(..., min_length=1, description="Họ và tên khách hàng")
    email: Optional[EmailStr] = Field(None, description="Email liên hệ")
    so_dien_thoai: str = Field(..., min_length=8, description="Số điện thoại")
    nguon: Optional[str] = Field(None, description="Nguồn tiếp cận (Facebook, Website, Referral...)")
    mon_hoc_quan_tam_id: Optional[int] = Field(None, description="ID môn học quan tâm")
    ghi_chu: Optional[str] = None

class LeadUpdate(BaseModel):
    ho_ten: Optional[str] = None
    email: Optional[EmailStr] = None
    so_dien_thoai: Optional[str] = None
    nguon: Optional[str] = None
    mon_hoc_quan_tam_id: Optional[int] = None
    ghi_chu: Optional[str] = None
    trang_thai: Optional[str] = Field(None, description="Trạng thái (Moi, DangTuVan, ThanhCong, DaHuy)")
    ly_do_tu_choi: Optional[str] = Field(None, description="Lý do từ chối (bắt buộc khi trạng thái là TuChoi)")
    nguoi_phu_trach_id: Optional[int] = None
