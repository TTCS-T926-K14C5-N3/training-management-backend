from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, time

# --- SCHEMA MẪU LỊCH HỌC ---
class MauLichHocCreate(BaseModel):
    ten_mau: str = Field(..., description="Tên mẫu lịch (Ví dụ: Thứ 2-4-6 Ca Tối)")
    thu_trong_tuan: List[int] = Field(..., description="Danh sách các thứ (2 đến 8 với 8 là CN)")
    gio_bat_dau: time = Field(..., description="Giờ bắt đầu")
    gio_ket_thuc: time = Field(..., description="Giờ kết thúc")

class MauLichHocResponse(MauLichHocCreate):
    id: int

    class Config:
        from_attributes = True


# --- SCHEMA NGÀY NGHĨ ---
class NgayNghiCreate(BaseModel):
    ten_ngay_nghi: str = Field(..., description="Tên dịp lễ/ngày nghỉ")
    ngay_bat_dau: date = Field(..., description="Ngày bắt đầu nghỉ")
    ngay_ket_thuc: date = Field(..., description="Ngày kết thúc nghỉ")
    ghi_chu: Optional[str] = Field(None, description="Ghi chú chi tiết")

class NgayNghiResponse(NgayNghiCreate):
    id: int

    class Config:
        from_attributes = True