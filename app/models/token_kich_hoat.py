from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
)

from app.database import Base


class TokenKichHoat(Base):
    __tablename__ = "TokenKichHoat"

    TokenKichHoatId = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    NguoiDungId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )

    Token = Column(
        String(255),
        nullable=False,
        unique=True,
    )

    ThoiGianTao = Column(
        DateTime,
        nullable=False,
    )

    ThoiGianHetHan = Column(
        DateTime,
        nullable=False,
    )

    DaSuDung = Column(
        Boolean,
        nullable=False,
        default=False,
    )