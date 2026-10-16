from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List

from app.database import get_db
from app.models.thoi_khoa_bieu import ThoiKhoaBieu
from app.schemas.thoi_khoa_bieu import SinhThoiKhoaBieuRequest
from app.core.security import require_permission

router = APIRouter(
    prefix="/thoi-khoa-bieu",
    tags=["Quản lý Thời khóa biểu"]
)

@router.post(
    "/sinh-tu-dong",
    summary="Tự động sinh thời khóa biểu cho lớp học (SCRUM-371)",
    dependencies=[Depends(require_permission("SCHEDULE_MANAGE"))]
)
def generate_thoi_khoa_bieu(
    request: SinhThoiKhoaBieuRequest,
    db: Session = Depends(get_db)
):
    current_date = request.ngay_bat_dau
    buoi_da_sinh = 0
    danh_sach_buoi_hoc = []
    
    # Tập hợp các ngày nghỉ dạng set để tra cứu nhanh
    ngay_nghi_set = set(request.danh_sach_ngay_nghi or [])

    # Vòng lặp chạy cho đến khi sinh đủ số buổi học yêu cầu
    while buoi_da_sinh < request.tong_so_buoi:
        # Trong Python: isoweekday() trả về 1=Thứ 2, ..., 7=Chủ Nhật.
        # Nếu hệ thống tính Thứ 2=2, Chủ Nhật=8 thì cộng thêm 1.
        weekday = current_date.isoweekday() + 1
        
        # Nếu ngày hiện tại nằm trong thứ xếp lịch VÀ không phải ngày nghỉ
        if weekday in request.thu_trong_tuan and current_date not in ngay_nghi_set:
            buoi_hoc = ThoiKhoaBieu(
                LopHocId=request.lop_hoc_id,
                MonHocId=request.mon_hoc_id,
                GiangVienId=request.giang_vien_id,
                PhongHocId=request.phong_hoc_id,
                NgayHoc=current_date,
                GioBatDau=request.gio_bat_dau,
                GioKetThuc=request.gio_ket_thuc,
                TrangThai="Lên lịch"
            )
            danh_sach_buoi_hoc.append(buoi_hoc)
            buoi_da_sinh += 1

        # Tăng lên 1 ngày tiếp theo
        current_date += timedelta(days=1)

    # Lưu toàn bộ vào DB
    db.add_all(danh_sach_buoi_hoc)
    db.commit()

    return {
        "message": f"Đã sinh thành công {buoi_da_sinh} buổi học cho lớp!",
        "lopHocId": request.lop_hoc_id,
        "ngayBatDau": request.ngay_bat_dau,
        "ngayKetThuc": danh_sach_buoi_hoc[-1].NgayHoc if danh_sach_buoi_hoc else None
    }