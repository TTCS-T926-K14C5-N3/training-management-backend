from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class NhatKyLeadCreate(BaseModel):
    phuong_thuc: str = Field(..., min_length=1, description="GoiDien, Email, GapTrucTiep, Zalo")
    noi_dung: str = Field(..., min_length=1, description="Nội dung chăm sóc")
    ket_qua: Optional[str] = Field(None, description="Kết quả đạt được")

class NhatKyLeadResponse(BaseModel):
    nhat_ky_id: int = Field(..., alias="NhatKyId")
    lead_id: int = Field(..., alias="LeadId")
    nguoi_thuc_hien_id: Optional[int] = Field(None, alias="NguoiThucHienId")
    phuong_thuc: str = Field(..., alias="PhuongThuc")
    noi_dung: str = Field(..., alias="NoiDung")
    ket_qua: Optional[str] = Field(None, alias="KetQua")
    ngay_cham_soc: datetime = Field(..., alias="NgayChamSoc")

    class Config:
        from_attributes = True
        populate_by_name = True