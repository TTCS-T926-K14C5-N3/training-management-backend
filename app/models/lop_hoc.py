from sqlalchemy import Column, DateTime, ForeignKey, Integer, Unicode

from app.database import Base


class LopHoc(Base):
    __tablename__ = "LopHoc"

    LopHocId = Column(Integer, primary_key=True, autoincrement=True)
    MaLop = Column(Unicode(30), nullable=False, unique=True)
    TenLop = Column(Unicode(100), nullable=False)
    NamHoc = Column(Unicode(9), nullable=False)
    GiangVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=True,
    )
    TrangThai = Column(
        Unicode(30),
        nullable=False,
        default="Đang hoạt động",
    )
    NgayTao = Column(DateTime, nullable=False)
