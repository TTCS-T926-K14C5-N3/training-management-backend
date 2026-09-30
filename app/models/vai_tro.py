from sqlalchemy import (
    Column,
    Integer,
    String
)

from app.database import Base


class VaiTro(Base):
    __tablename__ = "VaiTro"

    VaiTroId = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    TenVaiTro = Column(
        String(50),
        nullable=False
    )

    MoTa = Column(
        String(255),
        nullable=True
    )