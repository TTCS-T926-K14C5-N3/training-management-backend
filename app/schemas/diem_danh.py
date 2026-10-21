from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, time

class LichSuDiemDanhResponse(BaseModel):
    diem_danh_id: int
    thoi_khoa_bieu_id: int
    ngay_hoc: date
    gio_bat_dau: Optional[time] = None
    gio_ket_thuc: Optional[time] = None
    ten_mon_hoc: Optional[str] = None
    trang_thai_diem_danh: str = Field(..., description="Có mặt, Vắng mặt, Có phép, Muộn")
    ghi_chu: Optional[str] = None

    class Config:
        from_attributes = True