from datetime import date

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Unicode,
)

from app.database import Base


class LopHoc(Base):
    __tablename__ = "LopHoc"

    LopHocId = Column(Integer, primary_key=True, autoincrement=True)
    MaLop = Column(Unicode(30), nullable=False, unique=True)
    TenLop = Column(Unicode(150), nullable=False)
    NamHoc = Column(Unicode(9), nullable=False)
    ChuongTrinhId = Column(
        Integer,
        ForeignKey("ChuongTrinhDaoTao.ChuongTrinhId"),
        nullable=True,
    )
    GiangVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=True,
    )
    NgayKhaiGiang = Column(Date, nullable=False, default=date.today)
    SiSoToiDa = Column(Integer, nullable=False, default=30)
    HinhThuc = Column(Unicode(20), nullable=False, default="Trực tiếp")
    PhongHocId = Column(
        Integer,
        ForeignKey("PhongHoc.PhongHocId"),
        nullable=True,
    )
    LinkTrucTuyen = Column(Unicode(500), nullable=True)
    TienDo = Column(Numeric(5, 2), nullable=False, default=0)
    TrangThai = Column(
        Unicode(30),
        nullable=False,
        default="Chuẩn bị",
    )
    NgayTao = Column(DateTime, nullable=False)
