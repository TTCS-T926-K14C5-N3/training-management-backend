from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class BuoiHoc(Base):
    __tablename__ = "BuoiHoc"

    BuoiHocId = Column(Integer, primary_key=True, index=True, autoincrement=True)
    TenBuoiHoc = Column(String(255), nullable=False)
    MoTa = Column(Text, nullable=True)
    LopHocId = Column(Integer, ForeignKey("LopHoc.LopHocId"), nullable=False)
    GiangVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=True)
    PhongHoc = Column(String(100), nullable=True)
    ThoiGianBatDau = Column(DateTime, nullable=False)
    ThoiGianKetThuc = Column(DateTime, nullable=False)
    TrangThai = Column(String(50), default="ChuaBatDau")  # ChuaBatDau, DangXayRa, DaKetThuc, Huy
    NgayTao = Column(DateTime, default=datetime.now)
    NgayCapNhat = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships (Điều chỉnh tùy theo Model thực tế trong dự án)
    # lop_hoc = relationship("LopHoc", back_populates="buoi_hoc")
    # giang_vien = relationship("NguoiDung", back_populates="buoi_hoc_giang_day")