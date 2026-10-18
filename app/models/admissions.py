from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Unicode,
    String,
)

from app.database import Base


class AdmissionsLead(Base):
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
        nullable=True,
    )
    TrangThai = Column(Unicode(30), nullable=False)
    NgayTao = Column(DateTime, nullable=False)
    NgayCapNhat = Column(DateTime, nullable=False)
    NguoiTaoId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=True,
    )
    LyDoTuChoi = Column(Unicode(500), nullable=True)


class AdmissionsLeadAssignment(Base):
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


class AdmissionsLeadStatusHistory(Base):
    __tablename__ = "TuyenSinh_Lead_LichSuTrangThai"

    LichSuId = Column(Integer, primary_key=True, autoincrement=True)
    LeadId = Column(
        Integer,
        ForeignKey("TuyenSinh_Lead.LeadId"),
        nullable=False,
    )
    TrangThaiCu = Column(Unicode(30), nullable=True)
    TrangThaiMoi = Column(Unicode(30), nullable=False)
    LyDo = Column(Unicode(500), nullable=True)
    NguoiThucHienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    ThoiDiem = Column(DateTime, nullable=False)


class AdmissionsLeadInteraction(Base):
    __tablename__ = "TuyenSinh_Lead_TuongTac"

    TuongTacId = Column(Integer, primary_key=True, autoincrement=True)
    LeadId = Column(
        Integer,
        ForeignKey("TuyenSinh_Lead.LeadId"),
        nullable=False,
    )
    Loai = Column(Unicode(20), nullable=False)
    NoiDung = Column(Unicode(2000), nullable=False)
    ThoiDiem = Column(DateTime, nullable=False)
    HenGoiLaiLuc = Column(DateTime, nullable=True)
    NguoiThucHienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    NgayTao = Column(DateTime, nullable=False)
