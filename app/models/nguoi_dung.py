from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime
)

from app.database import Base


class NguoiDung(Base):
    __tablename__ = "NguoiDung"

    NguoiDungId = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    HoTen = Column(
        String(100),
        nullable=False
    )

    Email = Column(
        String(255),
        nullable=False,
        unique=True
    )

    SoDienThoai = Column(
        String(20),
        nullable=True
    )

    MatKhauHash = Column(
        String(255),
        nullable=False
    )

    TrangThai = Column(
        String(50),
        nullable=False
    )

    SoLanDangNhapSai = Column(
        Integer,
        nullable=False,
        default=0
    )

    KhoaDen = Column(
        DateTime,
        nullable=True
    )

    LyDoKhoa = Column(
        String(255),
        nullable=True
    )

    NgayTao = Column(
        DateTime,
        nullable=True
    )

    NgayCapNhat = Column(
        DateTime,
        nullable=True
    )

    TokenValidAfter = Column(
    DateTime,
    nullable=True
)