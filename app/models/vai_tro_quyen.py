from sqlalchemy import Column, ForeignKey, Integer

from app.database import Base


class VaiTroQuyen(Base):
    __tablename__ = "VaiTro_Quyen"

    VaiTroId = Column(
        Integer,
        ForeignKey("VaiTro.VaiTroId"),
        primary_key=True,
        nullable=False,
    )

    QuyenId = Column(
        Integer,
        ForeignKey("Quyen.QuyenId"),
        primary_key=True,
        nullable=False,
    )