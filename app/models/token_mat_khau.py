from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    DateTime,
    Boolean,
)

from app.database import Base


class TokenMatKhau(Base):
    __tablename__ = "TokenMatKhau"

    TokenId = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    NguoiDungId = Column(
        Integer,
        nullable=False
    )

    Token = Column(
        String(500),
        nullable=False
    )

    ThoiGianTao = Column(
        DateTime,
        nullable=False
    )

    ThoiGianHetHan = Column(
        DateTime,
        nullable=False
    )

    DaSuDung = Column(
        Boolean,
        nullable=False,
        default=False
    )