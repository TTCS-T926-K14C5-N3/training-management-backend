from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class TuyenSinhLeadChuyenDoi(Base):
    __tablename__ = "TuyenSinh_Lead_ChuyenDoi"

    LeadId = Column(Integer, primary_key=True)
    NguoiDungId = Column(Integer, nullable=False, unique=True)
    MaHocVien = Column(String(20), nullable=False, unique=True)
    ChuongTrinhId = Column(Integer, nullable=True)
    NgayNhapHoc = Column(DateTime, nullable=False)
    NguoiChuyenDoiId = Column(Integer, nullable=False)
