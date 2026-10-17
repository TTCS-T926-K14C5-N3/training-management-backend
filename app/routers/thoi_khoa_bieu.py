from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List

from app.database import get_db
from app.models.thoi_khoa_bieu import ThoiKhoaBieu
from app.schemas.thoi_khoa_bieu import SinhThoiKhoaBieuRequest
from app.core.security import require_permission
from app.schemas.thoi_khoa_bieu import (
    SinhThoiKhoaBieuRequest,
    BuoiHocPreviewItem,

    LuuThoiKhoaBieuRequest,
    GanBaiHocRequest

)
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
# 1. API Xem trước thời khóa biểu (Không lưu DB)
@router.post(
    "/xem-truoc",
    response_model=List[BuoiHocPreviewItem],
    summary="Xem trước danh sách buổi học dự kiến (SCRUM-372)",
    dependencies=[Depends(require_permission("SCHEDULE_MANAGE"))]
)
def preview_thoi_khoa_bieu(request: SinhThoiKhoaBieuRequest):
    current_date = request.ngay_bat_dau
    buoi_da_sinh = 0
    preview_list = []
    ngay_nghi_set = set(request.danh_sach_ngay_nghi or [])

    while buoi_da_sinh < request.tong_so_buoi:
        weekday = current_date.isoweekday() + 1
        
        if weekday in request.thu_trong_tuan and current_date not in ngay_nghi_set:
            buoi_da_sinh += 1
            preview_list.append(
                BuoiHocPreviewItem(
                    stt=buoi_da_sinh,
                    lop_hoc_id=request.lop_hoc_id,
                    mon_hoc_id=request.mon_hoc_id,
                    giang_vien_id=request.giang_vien_id,
                    phong_hoc_id=request.phong_hoc_id,
                    ngay_hoc=current_date,
                    gio_bat_dau=request.gio_bat_dau,
                    gio_ket_thuc=request.gio_ket_thuc
                )
            )

        current_date += timedelta(days=1)

    return preview_list


# 2. API Lưu thời khóa biểu chính thức sau khi kiểm tra
@router.post(
    "/luu-chinh-thuc",
    summary="Lưu chính thức thời khóa biểu vào Database (SCRUM-372)",
    dependencies=[Depends(require_permission("SCHEDULE_MANAGE"))]
)
def save_thoi_khoa_bieu(
    request: LuuThoiKhoaBieuRequest,
    db: Session = Depends(get_db)
):
    if not request.danh_sach_buoi_hoc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Danh sách buổi học không được để trống"
        )

    danh_sach_db = []
    for item in request.danh_sach_buoi_hoc:
        buoi_hoc = ThoiKhoaBieu(
            LopHocId=item.lop_hoc_id,
            MonHocId=item.mon_hoc_id,
            GiangVienId=item.giang_vien_id,
            PhongHocId=item.phong_hoc_id,
            NgayHoc=item.ngay_hoc,
            GioBatDau=item.gio_bat_dau,
            GioKetThuc=item.gio_ket_thuc,
            TrangThai="Lên lịch"
        )
        danh_sach_db.append(buoi_hoc)

    db.add_all(danh_sach_db)
    db.commit()

    return {
        "message": f"Đã lưu thành công {len(danh_sach_db)} buổi học vào hệ thống!",
        "tongSoBuoi": len(danh_sach_db)

    }
# API Gắn bài học vào một buổi học cụ thể
@router.put(
    "/{thoi_khoa_bieu_id}/gan-bai-hoc",
    summary="Gắn bài học vào buổi học trong thời khóa biểu (SCRUM-373)",
    dependencies=[Depends(require_permission("SCHEDULE_MANAGE"))]
)
def gan_bai_hoc(
    thoi_khoa_bieu_id: int,
    request: GanBaiHocRequest,
    db: Session = Depends(get_db)
):
    buoi_hoc = db.query(ThoiKhoaBieu).filter(ThoiKhoaBieu.ThoiKhoaBieuId == thoi_khoa_bieu_id).first()
    if not buoi_hoc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy buổi học trong thời khóa biểu"
        )

    if request.bai_hoc_id is not None:
        buoi_hoc.BaiHocId = request.bai_hoc_id
    if request.noi_dung_bai_hoc is not None:
        buoi_hoc.NoiDungBaiHoc = request.noi_dung_bai_hoc

    db.commit()
    db.refresh(buoi_hoc)
    return {
        "message": "Gắn bài học thành công!",
        "thoiKhoaBieuId": buoi_hoc.ThoiKhoaBieuId,
        "baiHocId": buoi_hoc.BaiHocId,
        "noiDungBaiHoc": buoi_hoc.NoiDungBaiHoc

    }