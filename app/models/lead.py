from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime
from app.database import Base


class Lead(Base):
    __tablename__ = "Lead"

    LeadId = Column(Integer, primary_key=True, index=True, autoincrement=True)
    HoTen = Column(String(255), nullable=False)
    Email = Column(String(255), nullable=True, index=True)
    SoDienThoai = Column(String(20), nullable=False, index=True)
    Nguon = Column(String(100), nullable=True)  # VD: Facebook, Website, Referral, Direct
    MonHocQuanTamId = Column(Integer, ForeignKey("MonHoc.MonHocId"), nullable=True)
    GhiChu = Column(Text, nullable=True)
    TrangThai = Column(String(50), default="Moi")  # Moi, DangTuVan, ThanhCong, DaHuy
    NguoiPhuTrachId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=True)
    NgayTao = Column(DateTime, default=datetime.now)
    NgayCapNhat = Column(DateTime, default=datetime.now, onupdate=datetime.now)