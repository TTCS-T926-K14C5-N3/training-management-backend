from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.core.security import require_permission
from app.models.buoi_hoc import BuoiHoc

router = APIRouter(
    prefix="/sessions",
    tags=["BuoiHoc"],
)

# ============================================================
# LẤY DANH SÁCH BUỔI HỌC (SCRUM-213)
# ============================================================

@router.get(
    "/",
    summary="Lấy danh sách các buổi học",
    dependencies=[
        Depends(require_permission("SESSION_VIEW"))
    ],
)
def get_buoi_hoc_list(
    lop_hoc_id: Optional[int] = Query(None, description="Lọc theo ID lớp học"),
    giang_vien_id: Optional[int] = Query(None, description="Lọc theo ID giảng viên"),
    db: Session = Depends(get_db),
):
    """
    API danh sách buổi học, có hỗ trợ lọc theo Lớp học hoặc Giảng viên
    """
    query = db.query(BuoiHoc)

    if lop_hoc_id is not None:
        query = query.filter(BuoiHoc.LopHocId == lop_hoc_id)

    if giang_vien_id is not None:
        query = query.filter(BuoiHoc.GiangVienId == giang_vien_id)

    buoi_hoc_list = query.order_by(BuoiHoc.ThoiGianBatDau.asc()).all()

    return [
        {
            "buoiHocId": item.BuoiHocId,
            "tenBuoiHoc": item.TenBuoiHoc,
            "moTa": item.MoTa,
            "lopHocId": item.LopHocId,
            "giangVienId": item.GiangVienId,
            "phongHoc": item.PhongHoc,
            "thoiGianBatDau": item.ThoiGianBatDau,
            "thoiGianKetThuc": item.ThoiGianKetThuc,
            "trangThai": item.TrangThai,
        }
        for item in buoi_hoc_list
    ]