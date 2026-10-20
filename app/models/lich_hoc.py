from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Time,
    Unicode,
    UnicodeText,
    text,
)

from app.database import Base


class LichHoc(Base):
    __tablename__ = "LichHoc"
    __table_args__ = (
        Index(
            "UX_LichHoc_LopHoc_BuoiHoc_DaLenLich",
            "LopHocId",
            "BuoiHocId",
            unique=True,
            mssql_where=text(
                "BuoiHocId IS NOT NULL AND TrangThai = N'Đã lên lịch'"
            ),
            sqlite_where=text(
                "BuoiHocId IS NOT NULL AND TrangThai = 'Đã lên lịch'"
            ),
        ),
    )

    LichHocId = Column(Integer, primary_key=True, autoincrement=True)
    LopHocId = Column(Integer, ForeignKey("LopHoc.LopHocId"), nullable=False)
    MonHocId = Column(Integer, ForeignKey("MonHoc.MonHocId"), nullable=False)
    BuoiHocId = Column(Integer, ForeignKey("BuoiHoc.BuoiHocId"), nullable=True)
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


class LichHocThongBao(Base):
    __tablename__ = "LichHoc_ThongBao"
    __table_args__ = (
        Index(
            "IX_LichHoc_ThongBao_NguoiNhan_ThoiDiem",
            "NguoiNhanId",
            "ThoiDiem",
        ),
    )

    LichHocThongBaoId = Column(Integer, primary_key=True, autoincrement=True)
    LichHocId = Column(
        Integer,
        ForeignKey("LichHoc.LichHocId"),
        nullable=False,
    )
    NguoiNhanId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    TieuDe = Column(Unicode(200), nullable=False)
    NoiDung = Column(UnicodeText, nullable=False)
    ThoiDiem = Column(DateTime, nullable=False)
