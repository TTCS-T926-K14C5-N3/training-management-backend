from fastapi import APIRouter, Depends, HTTPException, status, Query
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

# 1. Lấy danh sách Lead (SCRUM-236 & SCRUM-267)
@router.get(
    "/",
    summary="Lấy danh sách Lead",
    dependencies=[Depends(require_permission("LEAD_VIEW"))],
)
def get_lead_list(
    keyword: Optional[str] = Query(None),
    trang_thai: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
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
    return query.order_by(Lead.LeadId.desc()).all()


# 2. Tạo Lead mới (SCRUM-236 & SCRUM-267)
@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Tạo Lead mới",
    dependencies=[Depends(require_permission("LEAD_CREATE"))],
)
def create_lead(
    request: LeadCreate,
    db: Session = Depends(get_db),
):
    new_lead = Lead(
        HoTen=request.ho_ten.strip(),
        Email=str(request.email).strip() if request.email else None,
        SoDienThoai=request.so_dien_thoai.strip(),
        Nguon=request.nguon,
        MonHocQuanTamId=request.mon_hoc_quan_tam_id,
        GhiChu=request.ghi_chu,
        TrangThai="Moi",
    )
    db.add(new_lead)
    db.commit()
    db.refresh(new_lead)
    return new_lead


# 3. Cập nhật Lead & Xử lý Từ chối (SCRUM-237 & SCRUM-266 & SCRUM-267)
@router.put(
    "/{lead_id}",
    summary="Cập nhật thông tin Lead",
    dependencies=[Depends(require_permission("LEAD_UPDATE"))],
)
def update_lead(
    lead_id: int,
    request: LeadUpdate,
    db: Session = Depends(get_db),
):
    lead_obj = db.query(Lead).filter(Lead.LeadId == lead_id).first()
    if not lead_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin khách hàng tiềm năng"
        )

    # Quy tắc chuyển sang Từ chối (SCRUM-266)
    if request.trang_thai == "TuChoi":
        if not request.ly_do_tu_choi or not request.ly_do_tu_choi.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bắt buộc phải nhập lý do từ chối khi chuyển trạng thái sang 'Từ chối'."
            )
        lead_obj.TrangThai = "TuChoi"
        lead_obj.LyDoTuChoi = request.ly_do_tu_choi.strip()
    elif request.trang_thai is not None:
        lead_obj.TrangThai = request.trang_thai.strip()

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