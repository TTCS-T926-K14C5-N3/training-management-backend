from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import get_db
from app.core.security import require_permission
from app.models.mon_hoc import MonHoc

router = APIRouter(
    prefix="/mon-hoc",
    tags=["MonHoc"],
)

# 1. Lấy danh sách Môn học
@router.get(
    "/",
    summary="Lấy danh sách môn học",
    dependencies=[Depends(require_permission("ACADEMIC_VIEW"))],
)
def get_mon_hoc_list(
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(MonHoc)
    if keyword:
        search_pattern = f"%{keyword.strip()}%"
        query = query.filter(
            (MonHoc.TenMonHoc.ilike(search_pattern)) |
            (MonHoc.MaMonHoc.ilike(search_pattern))
        )
    return query.all()


# 2. Lấy chi tiết Môn học theo ID
@router.get(
    "/{mon_hoc_id}",
    summary="Lấy thông tin chi tiết môn học",
    dependencies=[Depends(require_permission("ACADEMIC_VIEW"))],
)
def get_mon_hoc_detail(
    mon_hoc_id: int,
    db: Session = Depends(get_db),
):
    mon_hoc = db.query(MonHoc).filter(MonHoc.MonHocId == mon_hoc_id).first()
    if not mon_hoc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông tin môn học"
        )
    return mon_hoc