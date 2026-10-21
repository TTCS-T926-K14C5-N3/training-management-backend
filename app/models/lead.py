from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Lead(Base):
    __tablename__ = "lead"

    LeadId = Column(Integer, primary_key=True, index=True, autoincrement=True)
    HoTen = Column(String(255), nullable=False)
    Email = Column(String(255), nullable=True)
    SoDienThoai = Column(String(20), nullable=False)
    Nguon = Column(String(100), nullable=True)
    MonHocQuanTamId = Column(Integer, nullable=True)
    GhiChu = Column(Text, nullable=True)
    TrangThai = Column(String(50), default="Moi", nullable=False)
    LyDoTuChoi = Column(Text, nullable=True)
    # --- PHẦN PHÂN CÔNG LEAD ---
    NguoiPhuTrachId = Column(Integer, ForeignKey("nguoi_dung.NguoiDungId"), nullable=True)
    NgayPhanCong = Column(DateTime, nullable=True)
    NgayTao = Column(DateTime, default=datetime.utcnow)
    # Relationships
    nguoi_phu_trach = relationship("NguoiDung", backref="leads_assigned", foreign_keys=[NguoiPhuTrachId])
    nhat_ky_danh_sach = relationship("NhatKyLead", back_populates="lead", cascade="all, delete-orphan")