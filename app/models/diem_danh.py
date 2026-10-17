from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Unicode,
    UnicodeText,
    UniqueConstraint,
)

from app.database import Base


class DiemDanh(Base):
    __tablename__ = "DiemDanh"
    __table_args__ = (
        UniqueConstraint(
            "LichHocId",
            "HocVienId",
            name="UQ_DiemDanh_LichHoc_HocVien",
        ),
    )

    DiemDanhId = Column(Integer, primary_key=True, autoincrement=True)
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
    TrangThai = Column(Unicode(20), nullable=False)
    GhiChu = Column(UnicodeText, nullable=True)
    NguoiDiemDanhId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    NgayCapNhat = Column(DateTime, nullable=False)