from sqlalchemy import Column, DateTime, ForeignKey, Integer

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
