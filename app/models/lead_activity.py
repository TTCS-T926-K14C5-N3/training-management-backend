from sqlalchemy import Column, DateTime, ForeignKey, Integer, Unicode

from app.database import Base


class LeadStatusHistory(Base):
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


class LeadInteraction(Base):
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
