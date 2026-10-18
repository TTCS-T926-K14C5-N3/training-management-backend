from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.database import Base


class TuyenSinhLeadChuyenDoi(Base):
    __tablename__ = "TuyenSinh_Lead_ChuyenDoi"

    LeadId = Column(
        Integer,
        ForeignKey("TuyenSinh_Lead.LeadId"),
        primary_key=True,
    )
    NguoiDungId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
        unique=True,
    )
    MaHocVien = Column(String(20), nullable=False, unique=True)
    ChuongTrinhId = Column(
        Integer,
        ForeignKey("ChuongTrinhDaoTao.ChuongTrinhId"),
        nullable=True,
    )
    NgayNhapHoc = Column(DateTime, nullable=False)
    NguoiChuyenDoiId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
