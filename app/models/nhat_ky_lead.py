from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class NhatKyLead(Base):
    __tablename__ = "nhat_ky_lead"

    NhatKyId = Column(Integer, primary_key=True, index=True, autoincrement=True)
    LeadId = Column(Integer, ForeignKey("lead.LeadId", ondelete="CASCADE"), nullable=False)
    NguoiThucHienId = Column(Integer, ForeignKey("nguoi_dung.NguoiDungId"), nullable=True)
    
    PhuongThuc = Column(String(50), nullable=False, description="GoiDien, Email, GapTrucTiep, Zalo")
    NoiDung = Column(Text, nullable=False)
    KetQua = Column(String(255), nullable=True)
    NgayChamSoc = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    lead = relationship("Lead", back_populates="nhat_ky_danh_sach")