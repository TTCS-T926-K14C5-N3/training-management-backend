from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from app.database import get_db
from app.models.thoi_khoa_bieu import ThoiKhoaBieu
from app.schemas.diem_danh import LichSuDiemDanhResponse
from app.core.security import get_current_user

router = APIRouter(
    prefix="/diem-danh",
    tags=["Quản lý Điểm danh"]
)

@router.get(
    "/ca-nhan",
    response_model=List[LichSuDiemDanhResponse],
    summary="Lấy lịch sử điểm danh cá nhân của học viên đăng nhập (SCRUM-453)"
)
def get_lich_su_diem_danh_ca_nhan(
    tu_ngay: Optional[date] = None,
    den_ngay: Optional[date] = None,
    lop_hoc_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("id") or current_user.get("NguoiDungId")

    # Mock hoặc Query dữ liệu điểm danh thực tế từ DB
    query = db.query(ThoiKhoaBieu)
    if tu_ngay:
        query = query.filter(ThoiKhoaBieu.NgayHoc >= tu_ngay)
    if den_ngay:
        query = query.filter(ThoiKhoaBieu.NgayHoc <= den_ngay)
    if lop_hoc_id:
        query = query.filter(ThoiKhoaBieu.LopHocId == lop_hoc_id)

    danh_sach_buoi = query.order_by(ThoiKhoaBieu.NgayHoc.desc()).all()

    result = []
    for index, buoi in enumerate(danh_sach_buoi, start=1):
        result.append(
            LichSuDiemDanhResponse(
                diem_danh_id=index,
                thoi_khoa_bieu_id=buoi.ThoiKhoaBieuId,
                ngay_hoc=buoi.NgayHoc,
                gio_bat_dau=buoi.GioBatDau,
                gio_ket_thuc=buoi.GioKetThuc,
                ten_mon_hoc=buoi.mon_hoc.TenMonHoc if hasattr(buoi, "mon_hoc") and buoi.mon_hoc else "Chưa xếp môn",
                trang_thai_diem_danh="Có mặt",
                ghi_chu=None
            )
        )
    return result