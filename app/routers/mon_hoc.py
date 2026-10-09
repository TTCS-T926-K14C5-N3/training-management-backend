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
from app.schemas.mon_hoc import MonHocCreate
from fastapi import HTTPException, status

# ============================================================
# TẠO MÔN HỌC MỚI (SCRUM-186)
# ============================================================

@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Tạo môn học mới",
    dependencies=[
        Depends(require_permission("COURSE_CREATE"))
    ],
)
def create_mon_hoc(
    request: MonHocCreate,
    db: Session = Depends(get_db),
):
    """
    API tạo môn học mới, kiểm tra trùng mã môn học
    """
    # 1. Kiểm tra mã môn học đã tồn tại chưa
    existing_course = db.query(MonHoc).filter(
        MonHoc.MaMonHoc == request.ma_mon_hoc.strip()
    ).first()
    
    if existing_course:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mã môn học '{request.ma_mon_hoc}' đã tồn tại trong hệ thống."
        )

    # 2. Khởi tạo đối tượng MonHoc mới
    new_course = MonHoc(
        MaMonHoc=request.ma_mon_hoc.strip(),
        TenMonHoc=request.ten_mon_hoc.strip(),
        SoTinChi=request.so_tin_chi,
        MoTa=request.mo_ta.strip() if request.mo_ta else None,
        TrangThai="HoatDong",
    )

    try:
        db.add(new_course)
        db.commit()
        db.refresh(new_course)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể tạo môn học mới."
        )

    return {
        "message": "Tạo môn học mới thành công",
        "monHocId": new_course.MonHocId,
        "maMonHoc": new_course.MaMonHoc,
        "tenMonHoc": new_course.TenMonHoc,
    }