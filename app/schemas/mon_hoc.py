from pydantic import BaseModel, Field
from typing import Optional


class MonHocCreate(BaseModel):
    ma_mon_hoc: str = Field(..., min_length=1, description="Mã môn học (không trùng lặp)")
    ten_mon_hoc: str = Field(..., min_length=1, description="Tên môn học")
    so_tin_chi: Optional[int] = Field(0, ge=0, description="Số tín chỉ / số đơn vị học trình")
    mo_ta: Optional[str] = None