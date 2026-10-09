from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.core.security import require_permission
from app.models.mon_hoc import MonHoc

router = APIRouter(
    prefix="/courses",
    tags=["MonHoc"],
)

# ============================================================
# LẤY DANH SÁCH MÔN HỌC (SCRUM-185)
# ============================================================

@router.get(
    "/",
    summary="Lấy danh sách môn học",
    dependencies=[
        Depends(require_permission("COURSE_VIEW"))
    ],
)
def get_mon_hoc_list(
    keyword: Optional[str] = Query(None, description="Tìm kiếm theo mã hoặc tên môn học"),
    trang_thai: Optional[str] = Query(None, description="Lọc theo trạng thái (HoatDong, NgungHoatDong)"),
    db: Session = Depends(get_db),
):
    """
    API lấy danh sách các môn học, hỗ trợ tìm kiếm và lọc trạng thái
    """
    query = db.query(MonHoc)

    if keyword:
        search_pattern = f"%{keyword.strip()}%"
        query = query.filter(
            (MonHoc.MaMonHoc.ilike(search_pattern)) | 
            (MonHoc.TenMonHoc.ilike(search_pattern))
        )

    if trang_thai:
        query = query.filter(MonHoc.TrangThai == trang_thai)

    mon_hoc_list = query.order_by(MonHoc.MonHocId.desc()).all()

    return [
        {
            "monHocId": item.MonHocId,
            "maMonHoc": item.MaMonHoc,
            "tenMonHoc": item.TenMonHoc,
            "soTinChi": item.SoTinChi,
            "moTa": item.MoTa,
            "trangThai": item.TrangThai,
            "ngayTao": item.NgayTao,
            "ngayCapNhat": item.NgayCapNhat,
        }
        for item in mon_hoc_list
    ]