from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.core.security import require_permission, get_current_user
from app.models.lead import Lead
from app.models.nhat_ky_lead import NhatKyLead
from app.models.nguoi_dung import NguoiDung
from app.schemas.nhat_ky_lead import NhatKyLeadCreate, NhatKyLeadResponse

router = APIRouter(
    prefix="/leads",
    tags=["NhatKyLead"],
)

# 1. Ghi nhật ký chăm sóc Lead (POST /leads/{lead_id}/nhat-ky)
@router.post(
    "/{lead_id}/nhat-ky",
    status_code=status.HTTP_201_CREATED,
    summary="Ghi nhật ký chăm sóc Lead",
    dependencies=[Depends(require_permission("LEAD_UPDATE"))],
)
def create_nhat_ky_lead(
    lead_id: int,
    request: NhatKyLeadCreate,
    db: Session = Depends(get_db),
    current_user: NguoiDung = Depends(get_current_user),
):
    lead_obj = db.query(Lead).filter(Lead.LeadId == lead_id).first()
    if not lead_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin Lead"
        )

    new_log = NhatKyLead(
        LeadId=lead_id,
        NguoiThucHienId=current_user.NguoiDungId if current_user else None,
        PhuongThuc=request.phuong_thuc.strip(),
        NoiDung=request.noi_dung.strip(),
        KetQua=request.ket_qua.strip() if request.ket_qua else None,
    )

    db.add(new_log)
    db.commit()
    db.refresh(new_log)
    return new_log


# 2. Xem danh sách nhật ký chăm sóc của Lead (GET /leads/{lead_id}/nhat-ky)
@router.get(
    "/{lead_id}/nhat-ky",
    summary="Lấy lịch sử nhật ký chăm sóc Lead",
    dependencies=[Depends(require_permission("LEAD_VIEW"))],
)
def get_nhat_ky_lead_list(
    lead_id: int,
    db: Session = Depends(get_db),
):
    lead_obj = db.query(Lead).filter(Lead.LeadId == lead_id).first()
    if not lead_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin Lead"
        )

    return db.query(NhatKyLead).filter(NhatKyLead.LeadId == lead_id).order_by(NhatKyLead.NhatKyId.desc()).all()