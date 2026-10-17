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

# --- SCHEMA SINH THỜI KHÓA BIỂU TỰ ĐỘNG ---
class SinhThoiKhoaBieuRequest(BaseModel):
    lop_hoc_id: int = Field(..., description="ID của Lớp học")
    mon_hoc_id: Optional[int] = Field(None, description="ID của Môn học")
    giang_vien_id: Optional[int] = Field(None, description="ID Giảng viên")
    phong_hoc_id: Optional[int] = Field(None, description="ID Phòng học")
    ngay_bat_dau: date = Field(..., description="Ngày bắt đầu khóa học")
    tong_so_buoi: int = Field(..., description="Tổng số buổi học cần sinh")
    thu_trong_tuan: List[int] = Field(..., description="Ví dụ: [2, 4, 6] cho Thứ 2, 4, 6 (Thứ 2=2, Chủ Nhật=8)")
    gio_bat_dau: time = Field(..., description="Giờ bắt đầu học")
    gio_ket_thuc: time = Field(..., description="Giờ kết thúc học")
    danh_sach_ngay_nghi: Optional[List[date]] = Field(default=[], description="Danh sách các ngày nghỉ/lễ cần bỏ qua")
    # --- SCHEMA CHO SCRUM-372: XEM TRƯỚC VÀ LƯU THỜI KHÓA BIỂU ---

class BuoiHocPreviewItem(BaseModel):
    stt: int
    lop_hoc_id: int
    mon_hoc_id: Optional[int] = None
    giang_vien_id: Optional[int] = None
    phong_hoc_id: Optional[int] = None
    ngay_hoc: date
    gio_bat_dau: time
    gio_ket_thuc: time

class LuuThoiKhoaBieuRequest(BaseModel):
    danh_sach_buoi_hoc: List[BuoiHocPreviewItem] = Field(..., description="Danh sách các buổi học cần lưu vào DB")

# --- SCHEMA CHO SCRUM-373: GẮN BÀI HỌC VÀO BUỔI HỌC ---

class GanBaiHocRequest(BaseModel):
    bai_hoc_id: Optional[int] = Field(None, description="ID của bài học trong chương trình đào tạo")
    noi_dung_bai_hoc: Optional[str] = Field(None, description="Mô tả/Chủ đề bài học cho buổi học")
# --- SCHEMA CHO SCRUM-406: LỊCH HỌC CÁ NHÂN HỌC VIÊN ---

class LichHocHocVienResponse(BaseModel):
    thoi_khoa_bieu_id: int
    lop_hoc_id: int
    mon_hoc_id: Optional[int] = None
    ten_mon_hoc: Optional[str] = None
    giang_vien_id: Optional[int] = None
    phong_hoc_id: Optional[int] = None
    ngay_hoc: date
    gio_bat_dau: time
    gio_ket_thuc: time
    trang_thai: str
    noi_dung_bai_hoc: Optional[str] = None

    class Config:
        from_attributes = True