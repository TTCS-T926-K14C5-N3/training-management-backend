from sqlalchemy import Column, Integer, String, Date, Time, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class ThoiKhoaBieu(Base):
    __tablename__ = "thoi_khoa_bieu"

    ThoiKhoaBieuId = Column(Integer, primary_key=True, index=True, autoincrement=True)
    LopHocId = Column(Integer, ForeignKey("lop_hoc.LopHocId"), nullable=False)
    MonHocId = Column(Integer, ForeignKey("mon_hoc.MonHocId"), nullable=True)
    GiangVienId = Column(Integer, ForeignKey("nguoi_dung.NguoiDungId"), nullable=True)
    PhongHocId = Column(Integer, ForeignKey("phong_hoc.PhongHocId"), nullable=True)
    
    NgayHoc = Column(Date, nullable=False)
    GioBatDau = Column(Time, nullable=False)
    GioKetThuc = Column(Time, nullable=False)
    GhiChu = Column(Text, nullable=True)
    TrangThai = Column(String(50), default="Lên lịch", nullable=False)  # LenLich, DaHoc, Huy, DoiLich
    BaiHocId = Column(Integer, nullable=True)
    NoiDungBaiHoc = Column(Text, nullable=True)
    NgayTao = Column(DateTime, default=datetime.utcnow)

    # Relationships (khai báo liên kết dữ liệu)
    lop_hoc = relationship("LopHoc", backref="danh_sach_thoi_khoa_bieu", foreign_keys=[LopHocId])
    giang_vien = relationship("NguoiDung", backref="lich_day_list", foreign_keys=[GiangVienId])