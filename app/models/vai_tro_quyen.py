from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    UniqueConstraint
)

from app.database import Base


class VaiTroQuyen(Base):
    __tablename__ = "VaiTroQuyen"

    VaiTroQuyenId = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    VaiTroId = Column(
        Integer,
        ForeignKey("VaiTro.VaiTroId"),
        nullable=False
    )

    QuyenId = Column(
        Integer,
        ForeignKey("Quyen.QuyenId"),
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "VaiTroId",
            "QuyenId",
            name="UQ_VaiTroQuyen"
        ),
    )