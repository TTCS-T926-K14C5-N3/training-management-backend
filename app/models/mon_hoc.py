from sqlalchemy import CheckConstraint, Column, Integer, Numeric, String, Unicode

from app.database import Base


class MonHoc(Base):
    __tablename__ = "MonHoc"
    __table_args__ = (
        CheckConstraint(
            "TrongSo >= 0 AND TrongSo <= 1",
            name="CK_MonHoc_TrongSo",
        ),
    )

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
