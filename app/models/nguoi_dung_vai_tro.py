from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    ForeignKey
)

from app.database import Base


class NguoiDungVaiTro(Base):
    __tablename__ = "NguoiDung_VaiTro"

    NguoiDungId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        primary_key=True
    )

    VaiTroId = Column(
        Integer,
        ForeignKey("VaiTro.VaiTroId"),
        primary_key=True
    )

    NgayGan = Column(
        DateTime,
        nullable=False
    )