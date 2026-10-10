from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.core.security import require_permission
from app.models.lead import Lead
from app.schemas.lead import LeadCreate, LeadUpdate

router = APIRouter(
    prefix="/leads",
    tags=["Lead"],
)

# ============================================================
# 1. LẤY DANH SÁCH LEAD (SCRUM-236)
# ============================================================

@router.get(
    "/",
    summary="Lấy danh sách Lead (Khách hàng tiềm năng)",
    dependencies=[
        Depends(require_permission("LEAD_VIEW"))
    ],
)
def get_lead_list(
    keyword: Optional[str] = Query(None, description="Tìm kiếm theo họ tên, email hoặc số điện thoại"),
    trang_thai: Optional[str] = Query(None, description="Lọc theo trạng thái (Moi, DangTuVan, ThanhCong, DaHuy)"),
    db: Session = Depends(get_db),
):
    """
    API lấy danh sách Lead, hỗ trợ tìm kiếm từ khóa và lọc trạng thái
    """
    query = db.query(Lead)

    if keyword:
        search_pattern = f"%{keyword.strip()}%"
        query = query.filter(
            (Lead.HoTen.ilike(search_pattern)) |
            (Lead.Email.ilike(search_pattern)) |
            (Lead.SoDienThoai.ilike(search_pattern))
        )

    if trang_thai:
        query = query.filter(Lead.TrangThai == trang_thai)

    lead_list = query.order_by(Lead.LeadId.desc()).all()

    return [
        {
            "leadId": item.LeadId,
            "hoTen": item.HoTen,
            "email": item.Email,
            "soDienThoai": item.SoDienThoai,
            "nguon": item.Nguon,
            "monHocQuanTamId": item.MonHocQuanTamId,
            "ghiChu": item.GhiChu,
            "trangThai": item.TrangThai,
            "nguoiPhuTrachId": item.NguoiPhuTrachId,
            "ngayTao": item.NgayTao,
            "ngayCapNhat": item.NgayCapNhat,
        }
        for item in lead_list
    ]


# ============================================================
# 2. TẠO LEAD MỚI (SCRUM-236)
# ============================================================

@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Tạo khách hàng tiềm năng mới (Lead)",
    dependencies=[
        Depends(require_permission("LEAD_CREATE"))
    ],
)
def create_lead(
    request: LeadCreate,
    db: Session = Depends(get_db),
):
    """
    API tiếp nhận và tạo thông tin Lead mới
    """
    new_lead = Lead(
        HoTen=request.ho_ten.strip(),
        Email=str(request.email).strip() if request.email else None,
        SoDienThoai=request.so_dien_thoai.strip(),
        Nguon=request.nguon.strip() if request.nguon else None,
        MonHocQuanTamId=request.mon_hoc_quan_tam_id,
        GhiChu=request.ghi_chu.strip() if request.ghi_chu else None,
        TrangThai="Moi",
    )

    try:
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể tạo thông tin khách hàng tiềm năng mới."
        )

    return {
        "message": "Tạo khách hàng tiềm năng thành công",
        "leadId": new_lead.LeadId,
        "hoTen": new_lead.HoTen,
        "soDienThoai": new_lead.SoDienThoai,
    }
# ============================================================
# CẬP NHẬT THÔNG TIN LEAD (SCRUM-237)
# ============================================================

@router.put(
    "/{lead_id}",
    summary="Cập nhật thông tin khách hàng tiềm năng (Lead)",
    dependencies=[
        Depends(require_permission("LEAD_UPDATE"))
    ],
)
def update_lead(
    lead_id: int,
    request: LeadUpdate,
    db: Session = Depends(get_db),
):
    """
    API cập nhật thông tin Lead (họ tên, trạng thái, người phụ trách...)
    """
    lead_obj = db.query(Lead).filter(Lead.LeadId == lead_id).first()
    if not lead_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin khách hàng tiềm năng"
        )

    if request.ho_ten is not None:
        lead_obj.HoTen = request.ho_ten.strip()
    if request.email is not None:
        lead_obj.Email = str(request.email).strip()
    if request.so_dien_thoai is not None:
        lead_obj.SoDienThoai = request.so_dien_thoai.strip()
    if request.nguon is not None:
        lead_obj.Nguon = request.nguon.strip()
    if request.mon_hoc_quan_tam_id is not None:
        lead_obj.MonHocQuanTamId = request.mon_hoc_quan_tam_id
    if request.ghi_chu is not None:
        lead_obj.GhiChu = request.ghi_chu.strip()
    if request.trang_thai is not None:
        lead_obj.TrangThai = request.trang_thai.strip()
    if request.nguoi_phu_trach_id is not None:
        lead_obj.NguoiPhuTrachId = request.nguoi_phu_trach_id

    try:
        db.commit()
        db.refresh(lead_obj)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể cập nhật thông tin khách hàng tiềm năng."
        )

    return {
        "message": "Cập nhật thông tin Lead thành công",
        "leadId": lead_obj.LeadId,
        "hoTen": lead_obj.HoTen,
        "trangThai": lead_obj.TrangThai,
    }