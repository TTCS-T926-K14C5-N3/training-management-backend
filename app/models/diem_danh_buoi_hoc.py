from sqlalchemy import Column, DateTime, ForeignKey, Integer, Unicode, UnicodeText, UniqueConstraint

from app.database import Base


class DiemDanhBuoiHoc(Base):
    __tablename__ = "DiemDanh_BuoiHoc"
    __table_args__ = (
        UniqueConstraint(
            "LichHocId",
            "HocVienId",
            name="UQ_DiemDanh_BuoiHoc_LichHoc_HocVien",
        ),
    )

    DiemDanhBuoiHocId = Column(Integer, primary_key=True, autoincrement=True)
    LichHocId = Column(
        Integer,
        ForeignKey("LichHoc.LichHocId"),
        nullable=False,
    )
    HocVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    TrangThai = Column(Unicode(30), nullable=False)
    GhiChu = Column(UnicodeText, nullable=True)
    NgayCapNhat = Column(DateTime, nullable=False)
    NguoiCapNhatId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )


class DiemDanhBuoiHocLichSu(Base):
    __tablename__ = "DiemDanh_BuoiHoc_LichSu"

    LichSuId = Column(Integer, primary_key=True, autoincrement=True)
    LichHocId = Column(Integer, ForeignKey("LichHoc.LichHocId"), nullable=False)
    HocVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    TrangThaiCu = Column(Unicode(30), nullable=True)
    TrangThaiMoi = Column(Unicode(30), nullable=True)
    GhiChu = Column(Unicode(1000), nullable=True)
    NguoiThucHienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    ThoiDiem = Column(DateTime, nullable=False)
