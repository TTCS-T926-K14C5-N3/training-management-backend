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
# --- SCHEMA CHO SCRUM-454: THỐNG KÊ CHUYÊN CẦN ---

class ThongKeChuyenCanResponse(BaseModel):
    hoc_vien_id: int
    tong_so_buoi: int
    so_buoi_co_mat: int
    so_buoi_vang: int
    so_buoi_phep: int
    so_buoi_muon: int
    ty_le_chuyen_can: float = Field(..., description="Tỷ lệ chuyên cần tính theo %")
    dieu_kien_du_thi: bool = Field(..., description="Đạt điều kiện dự thi hay không (vd: >= 80%)")

    class Config:
        from_attributes = True