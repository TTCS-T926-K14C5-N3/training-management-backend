from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Unicode
from sqlalchemy.orm import synonym

from app.database import Base


class LopHocHocVien(Base):
    __tablename__ = "LopHoc_HocVien"

    LopHocId = Column(
        Integer,
        ForeignKey("LopHoc.LopHocId"),
        primary_key=True,
    )
    HocVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        primary_key=True,
    )
    NgayThamGia = Column(DateTime, nullable=False)
    NguoiGhiDanhId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=True,
    )
    TrangThaiGhiDanh = Column(
        Unicode(20),
        nullable=False,
        default="Đang học",
    )
    NgayKetThuc = Column(DateTime, nullable=True)


class LopHocHocVienThaoTac(Base):
    __tablename__ = "LopHoc_HocVien_ThaoTac"

    ThaoTacId = Column(Integer, primary_key=True, autoincrement=True)
    ActionId = synonym("ThaoTacId")
    LopHocId = Column(Integer, ForeignKey("LopHoc.LopHocId"), nullable=False)
    HocVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    LoaiThaoTac = Column(Unicode(20), nullable=False)
    NgayHieuLuc = Column(Date, nullable=False)
    LopHocDichId = Column(Integer, ForeignKey("LopHoc.LopHocId"), nullable=True)
    LyDo = Column(Unicode(1000), nullable=False)
    NguoiThucHienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    NgayTao = Column(DateTime, nullable=False)
