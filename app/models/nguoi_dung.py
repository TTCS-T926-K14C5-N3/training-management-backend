from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NguoiDung(Base):
    __tablename__ = "NguoiDung"

    NguoiDungId: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    HoTen: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    Email: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False
    )

    SoDienThoai: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    MatKhauHash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    TrangThai: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="HoatDong"
    )

    SoLanDangNhapSai: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    KhoaDen: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    LyDoKhoa: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    NgayTao: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now
    )

    NgayCapNhat: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )