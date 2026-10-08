from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Unicode,
)

from app.database import Base


class Lead(Base):
    __tablename__ = "TuyenSinh_Lead"

    LeadId = Column(Integer, primary_key=True, autoincrement=True)
    HoTen = Column(Unicode(100), nullable=False)
    SoDienThoai = Column(String(30), nullable=False)
    Email = Column(String(255), nullable=True)
    Nguon = Column(Unicode(100), nullable=False)
    GhiChu = Column(Unicode(1000), nullable=True)
    ChuongTrinhId = Column(
        Integer,
        ForeignKey("ChuongTrinhDaoTao.ChuongTrinhId"),
        nullable=False,
    )
    TrangThai = Column(Unicode(30), nullable=False, default="Mới")
    NgayTao = Column(DateTime, nullable=False)
    NgayCapNhat = Column(DateTime, nullable=False)
    NguoiTaoId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=True,
    )


class LeadAssignmentHistory(Base):
    __tablename__ = "TuyenSinh_Lead_PhanCong"

    PhanCongId = Column(Integer, primary_key=True, autoincrement=True)
    LeadId = Column(
        Integer,
        ForeignKey("TuyenSinh_Lead.LeadId"),
        nullable=False,
    )
    NguoiDungId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    NguoiPhanCongId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    NgayPhanCong = Column(DateTime, nullable=False)
    NgayBoPhanCong = Column(DateTime, nullable=True)
    DangPhanCong = Column(Boolean, nullable=False, default=True)
