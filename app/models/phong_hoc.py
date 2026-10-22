from sqlalchemy import CheckConstraint, Column, Integer, Unicode

from app.database import Base


class PhongHoc(Base):
    __tablename__ = "PhongHoc"

    PhongHocId = Column(Integer, primary_key=True, autoincrement=True)
    MaPhong = Column(Unicode(30), nullable=False, unique=True)
    TenPhong = Column(Unicode(100), nullable=False)
    SucChua = Column(Integer, nullable=False)
    LoaiPhong = Column(Unicode(20), nullable=False, default="Trực tiếp")
    TrangThai = Column(Unicode(20), nullable=False, default="Đang hoạt động")

    __table_args__ = (
        CheckConstraint(
            "LoaiPhong IN ('Trực tiếp', 'Trực tuyến')",
            name="CK_PhongHoc_LoaiPhong",
        ),
        CheckConstraint("SucChua > 0", name="CK_PhongHoc_SucChua"),
    )
