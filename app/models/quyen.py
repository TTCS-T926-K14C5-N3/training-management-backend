from sqlalchemy import (
    Column,
    Integer,
    String,
    Unicode,
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
        Unicode(150),
        nullable=False
    )

    MoTa = Column(
        Unicode(255),
        nullable=True
    )