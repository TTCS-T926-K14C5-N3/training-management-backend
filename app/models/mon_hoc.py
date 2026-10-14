from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from app.database import Base


class MonHoc(Base):
    __tablename__ = "MonHoc"

    MonHocId = Column(Integer, primary_key=True, index=True, autoincrement=True)
    MaMonHoc = Column(String(50), unique=True, nullable=False, index=True)
    TenMonHoc = Column(String(255), nullable=False)
    SoTinChi = Column(Integer, nullable=True, default=0)
    MoTa = Column(Text, nullable=True)
    TrangThai = Column(String(50), default="HoatDong")  # HoatDong, NgungHoatDong
    NgayTao = Column(DateTime, default=datetime.now)
    NgayCapNhat = Column(DateTime, default=datetime.now, onupdate=datetime.now)