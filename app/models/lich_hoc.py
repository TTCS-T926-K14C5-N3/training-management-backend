from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Time,
    Unicode,
    UnicodeText,
)

from app.database import Base


class LichHoc(Base):
    __tablename__ = "LichHoc"

    LichHocId = Column(Integer, primary_key=True, autoincrement=True)
    LopHocId = Column(Integer, ForeignKey("LopHoc.LopHocId"), nullable=False)
    MonHocId = Column(Integer, ForeignKey("MonHoc.MonHocId"), nullable=False)
    NgayHoc = Column(Date, nullable=False)
    GioBatDau = Column(Time, nullable=False)
    GioKetThuc = Column(Time, nullable=False)
    PhongHocId = Column(Integer, ForeignKey("PhongHoc.PhongHocId"), nullable=True)
    GiangVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    TrangThai = Column(Unicode(20), nullable=False, default="Đã lên lịch")
    LyDoHuy = Column(Unicode(1000), nullable=True)
    NgayTao = Column(DateTime, nullable=False)
    NguoiTaoId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    NgayCapNhat = Column(DateTime, nullable=False)
    NguoiCapNhatId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    NgayHuy = Column(DateTime, nullable=True)
    NguoiHuyId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=True)


class LichHocLichSu(Base):
    __tablename__ = "LichHoc_LichSu"

    LichHocLichSuId = Column(Integer, primary_key=True, autoincrement=True)
    LichHocId = Column(
        Integer,
        ForeignKey("LichHoc.LichHocId"),
        nullable=False,
    )
    HanhDong = Column(Unicode(20), nullable=False)
    DuLieuCu = Column(UnicodeText, nullable=True)
    DuLieuMoi = Column(UnicodeText, nullable=True)
    LyDo = Column(Unicode(1000), nullable=True)
    ThoiDiem = Column(DateTime, nullable=False)
    NguoiThucHienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
