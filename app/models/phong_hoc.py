from sqlalchemy import Column, Integer, Unicode

from app.database import Base


class PhongHoc(Base):
    __tablename__ = "PhongHoc"

    PhongHocId = Column(Integer, primary_key=True, autoincrement=True)
    MaPhong = Column(Unicode(30), nullable=False, unique=True)
    TenPhong = Column(Unicode(100), nullable=False)
    SucChua = Column(Integer, nullable=False)
    TrangThai = Column(Unicode(20), nullable=False, default="Đang hoạt động")
