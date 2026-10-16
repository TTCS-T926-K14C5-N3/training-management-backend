from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.schemas.thoi_khoa_bieu import (
    MauLichHocCreate, MauLichHocResponse,
    NgayNghiCreate, NgayNghiResponse
)
from app.core.security import require_permission

router = APIRouter(
    prefix="/lich-hoc-mau",
    tags=["Quản lý mẫu lịch học & Ngày nghỉ"]
)

# Mock DB lưu trữ dữ liệu tạm thời/kiểm thử
mau_lich_db = []
ngay_nghi_db = []

# --- API MẪU LỊCH HỌC ---
@router.post(
    "/mau-lich",
    response_model=MauLichHocResponse,
    summary="Tạo mẫu lịch học mới",
    dependencies=[Depends(require_permission("SCHEDULE_MANAGE"))]
)
def create_mau_lich(request: MauLichHocCreate):
    item = {
        "id": len(mau_lich_db) + 1,
        "ten_mau": request.ten_mau,
        "thu_trong_tuan": request.thu_trong_tuan,
        "gio_bat_dau": request.gio_bat_dau,
        "gio_ket_thuc": request.gio_ket_thuc
    }
    mau_lich_db.append(item)
    return item

@router.get(
    "/mau-lich",
    response_model=List[MauLichHocResponse],
    summary="Danh sách mẫu lịch học"
)
def get_danh_sach_mau_lich():
    return mau_lich_db


# --- API NGÀY NGHĨ ---
@router.post(
    "/ngay-nghi",
    response_model=NgayNghiResponse,
    summary="Thêm ngày nghỉ/lễ",
    dependencies=[Depends(require_permission("SCHEDULE_MANAGE"))]
)
def create_ngay_nghi(request: NgayNghiCreate):
    item = {
        "id": len(ngay_nghi_db) + 1,
        "ten_ngay_nghi": request.ten_ngay_nghi,
        "ngay_bat_dau": request.ngay_bat_dau,
        "ngay_ket_thuc": request.ngay_ket_thuc,
        "ghi_chu": request.ghi_chu
    }
    ngay_nghi_db.append(item)
    return item

@router.get(
    "/ngay-nghi",
    response_model=List[NgayNghiResponse],
    summary="Danh sách ngày nghỉ"
)
def get_danh_sach_ngay_nghi():
    return ngay_nghi_db