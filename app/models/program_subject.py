from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Unicode,
)

from app.database import Base


class ChuongTrinhMonHoc(Base):
    __tablename__ = "ChuongTrinh_MonHoc"
    __table_args__ = (
        UniqueConstraint(
            "ChuongTrinhId",
            "MonHocId",
            name="UQ_ChuongTrinh_MonHoc",
        ),
        UniqueConstraint(
            "ChuongTrinhId",
            "ThuTu",
            name="UQ_ChuongTrinh_MonHoc_ThuTu",
        ),
        CheckConstraint("ThuTu > 0", name="CK_ChuongTrinh_MonHoc_ThuTu"),
    )

    ChuongTrinhMonHocId = Column(Integer, primary_key=True, autoincrement=True)
    ChuongTrinhId = Column(
        Integer,
        ForeignKey("ChuongTrinhDaoTao.ChuongTrinhId"),
        nullable=False,
    )
    MonHocId = Column(
        Integer,
        ForeignKey("MonHoc.MonHocId"),
        nullable=False,
    )
    ThuTu = Column(Integer, nullable=False)


class ChuongTrinhMonHocTienQuyet(Base):
    __tablename__ = "ChuongTrinh_MonHoc_TienQuyet"

    ChuongTrinhMonHocId = Column(
        Integer,
        ForeignKey("ChuongTrinh_MonHoc.ChuongTrinhMonHocId"),
        primary_key=True,
    )
    MonTienQuyetId = Column(
        Integer,
        ForeignKey("ChuongTrinh_MonHoc.ChuongTrinhMonHocId"),
        primary_key=True,
    )


class BuoiHoc(Base):
    __tablename__ = "BuoiHoc"
    __table_args__ = (
        UniqueConstraint(
            "ChuongTrinhMonHocId",
            "SoThuTu",
            name="UQ_BuoiHoc_ChuongTrinhMonHoc_ThuTu",
        ),
        CheckConstraint("SoThuTu > 0", name="CK_BuoiHoc_SoThuTu"),
    )

    BuoiHocId = Column(Integer, primary_key=True, autoincrement=True)
    ChuongTrinhMonHocId = Column(
        Integer,
        ForeignKey("ChuongTrinh_MonHoc.ChuongTrinhMonHocId"),
        nullable=False,
    )
    SoThuTu = Column(Integer, nullable=False)
    ChuDe = Column(Unicode(200), nullable=False)
    MucTieu = Column(Unicode(1000), nullable=True)
