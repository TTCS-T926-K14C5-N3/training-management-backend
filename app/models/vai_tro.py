from sqlalchemy import (
    Column,
    Integer,
    Unicode,
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
        Unicode(50),
        nullable=False
    )

    MoTa = Column(
        Unicode(255),
        nullable=True
    )