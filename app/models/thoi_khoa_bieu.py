from datetime import datetime, timezone

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


class ThoiKhoaBieu(Base):
    __tablename__ = "ThoiKhoaBieu"

    ThoiKhoaBieuId = Column(Integer, primary_key=True, autoincrement=True)
    LopHocId = Column(Integer, ForeignKey("LopHoc.LopHocId"), nullable=False)
    MonHocId = Column(Integer, ForeignKey("MonHoc.MonHocId"), nullable=False)
    GiangVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    PhongHocId = Column(
        Integer,
        ForeignKey("PhongHoc.PhongHocId"),
        nullable=False,
    )
    NgayHoc = Column(Date, nullable=False)
    GioBatDau = Column(Time, nullable=False)
    GioKetThuc = Column(Time, nullable=False)
    TrangThai = Column(Unicode(20), nullable=False, default="Lên lịch")
    BaiHocId = Column(Integer, nullable=True)
    NoiDungBaiHoc = Column(Unicode(1000), nullable=True)
    LyDoHuy = Column(Unicode(1000), nullable=True)
    NgayHuy = Column(DateTime, nullable=True)
    NguoiHuyId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=True)
    NgayTao = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    NguoiTaoId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=True)
    NgayCapNhat = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    NguoiCapNhatId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=True,
    )


class ThoiKhoaBieuLichSu(Base):
    __tablename__ = "ThoiKhoaBieu_LichSu"

    ThoiKhoaBieuLichSuId = Column(Integer, primary_key=True, autoincrement=True)
    ThoiKhoaBieuId = Column(
        Integer,
        ForeignKey("ThoiKhoaBieu.ThoiKhoaBieuId"),
        nullable=False,
    )
    HanhDong = Column(Unicode(20), nullable=False)
    DuLieuCu = Column(UnicodeText, nullable=True)
    DuLieuMoi = Column(UnicodeText, nullable=True)
    LyDo = Column(Unicode(1000), nullable=True)
    ThoiDiem = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    NguoiThucHienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )


class ThoiKhoaBieuDiemDanh(Base):
    __tablename__ = "ThoiKhoaBieu_DiemDanh"

    ThoiKhoaBieuDiemDanhId = Column(Integer, primary_key=True, autoincrement=True)
    ThoiKhoaBieuId = Column(
        Integer,
        ForeignKey("ThoiKhoaBieu.ThoiKhoaBieuId"),
        nullable=False,
    )
    HocVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    TrangThai = Column(Unicode(20), nullable=False)
    GhiChu = Column(UnicodeText, nullable=True)
    NguoiDiemDanhId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    NgayCapNhat = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
