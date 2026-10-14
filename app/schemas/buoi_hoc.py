from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class BuoiHocBase(BaseModel):
    ten_buoi_hoc: str
    mo_ta: Optional[str] = None
    lop_hoc_id: int
    giang_vien_id: Optional[int] = None
    phong_hoc: Optional[str] = None
    thoi_gian_bat_dau: datetime
    thoi_gian_ket_thuc: datetime


class BuoiHocCreate(BuoiHocBase):
    pass


class BuoiHocUpdate(BaseModel):
    ten_buoi_hoc: Optional[str] = None
    mo_ta: Optional[str] = None
    giang_vien_id: Optional[int] = None
    phong_hoc: Optional[str] = None
    thoi_gian_bat_dau: Optional[datetime] = None
    thoi_gian_ket_thuc: Optional[datetime] = None
    trang_thai: Optional[str] = None