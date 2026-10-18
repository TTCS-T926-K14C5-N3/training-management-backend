from sqlalchemy import Column, Integer, Numeric, String, Unicode

from app.database import Base


class MonHoc(Base):
    __tablename__ = "MonHoc"

    MonHocId = Column(Integer, primary_key=True, autoincrement=True)
    MaMonHoc = Column(String(30), nullable=False, unique=True)
    TenMonHoc = Column(Unicode(150), nullable=False)
    SoTinChi = Column(Integer, nullable=True)
    SoBuoi = Column(Integer, nullable=False, default=1)
    TrongSo = Column(Numeric(5, 2), nullable=False, default=1)
    MoTaChuanDauRa = Column(Unicode(1000), nullable=True)
    TrangThai = Column(
        Unicode(30),
        nullable=False,
        default="Đang hoạt động",
    )
