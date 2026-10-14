from pydantic import BaseModel
from typing import Optional

class VaiTroBase(BaseModel):
    ten_vai_tro: str
    mo_ta: Optional[str] = None

class VaiTroResponse(VaiTroBase):
    id: int

    class Config:
        from_attributes = True