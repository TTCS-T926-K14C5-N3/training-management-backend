from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.core.security import require_permission
from app.models.buoi_hoc import BuoiHoc
from app.schemas.buoi_hoc import BuoiHocCreate, BuoiHocUpdate

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


# ============================================================
# THÊM BUỔI HỌC (SCRUM-214)
# ============================================================

@router.post(
    "/",
    status_code=201,
    summary="Thêm buổi học mới",
    dependencies=[Depends(require_permission("SESSION_CREATE"))],
)
def create_buoi_hoc(
    request: BuoiHocCreate,
    db: Session = Depends(get_db),
):
    new_session = BuoiHoc(
        TenBuoiHoc=request.ten_buoi_hoc,
        MoTa=request.mo_ta,
        LopHocId=request.lop_hoc_id,
        GiangVienId=request.giang_vien_id,
        PhongHoc=request.phong_hoc,
        ThoiGianBatDau=request.thoi_gian_bat_dau,
        ThoiGianKetThuc=request.thoi_gian_ket_thuc,
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {
        "message": "Tạo buổi học thành công",
        "buoiHocId": new_session.BuoiHocId,
    }


# ============================================================
# CẬP NHẬT BUỔI HỌC (SCRUM-214)
# ============================================================

@router.put(
    "/{buoi_hoc_id}",
    summary="Cập nhật thông tin buổi học",
    dependencies=[Depends(require_permission("SESSION_UPDATE"))],
)
def update_buoi_hoc(
    buoi_hoc_id: int,
    request: BuoiHocUpdate,
    db: Session = Depends(get_db),
):
    session_obj = db.query(BuoiHoc).filter(BuoiHoc.BuoiHocId == buoi_hoc_id).first()
    if not session_obj:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi học")

    if request.ten_buoi_hoc is not None:
        session_obj.TenBuoiHoc = request.ten_buoi_hoc
    if request.mo_ta is not None:
        session_obj.MoTa = request.mo_ta
    if request.giang_vien_id is not None:
        session_obj.GiangVienId = request.giang_vien_id
    if request.phong_hoc is not None:
        session_obj.PhongHoc = request.phong_hoc
    if request.thoi_gian_bat_dau is not None:
        session_obj.ThoiGianBatDau = request.thoi_gian_bat_dau
    if request.thoi_gian_ket_thuc is not None:
        session_obj.ThoiGianKetThuc = request.thoi_gian_ket_thuc
    if request.trang_thai is not None:
        session_obj.TrangThai = request.trang_thai

    db.commit()
    db.refresh(session_obj)

    return {
        "message": "Cập nhật buổi học thành công",
        "buoiHocId": session_obj.BuoiHocId,
    }


# ============================================================
# XÓA BUỔI HỌC (SCRUM-214)
# ============================================================

@router.delete(
    "/{buoi_hoc_id}",
    summary="Xóa buổi học",
    dependencies=[Depends(require_permission("SESSION_DELETE"))],
)
def delete_buoi_hoc(
    buoi_hoc_id: int,
    db: Session = Depends(get_db),
):
    session_obj = db.query(BuoiHoc).filter(BuoiHoc.BuoiHocId == buoi_hoc_id).first()
    if not session_obj:
        raise HTTPException(status_code=404, detail="Không tìm thấy buổi học")

    db.delete(session_obj)
    db.commit()

    return {
        "message": "Xóa buổi học thành công",
        "buoiHocId": buoi_hoc_id,
    }