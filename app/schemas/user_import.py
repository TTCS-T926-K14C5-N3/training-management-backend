from pydantic import BaseModel
from typing import List


class ImportUserRow(BaseModel):
    row: int
    hoTen: str
    email: str
    vaiTro: str
    vaiTroId: int | None = None
    valid: bool
    errors: List[str]


class ImportUserPreviewResponse(BaseModel):
    total: int
    valid: int
    invalid: int
    rows: List[ImportUserRow]
    