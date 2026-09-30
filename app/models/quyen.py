from sqlalchemy import (
    Column,
    Integer,
    String
)

from app.database import Base


class Quyen(Base):
    __tablename__ = "Quyen"

    QuyenId = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    MaQuyen = Column(
        String(100),
        nullable=False,
        unique=True
    )

    TenQuyen = Column(
        String(150),
        nullable=False
    )

    MoTa = Column(
        String(255),
        nullable=True
    )