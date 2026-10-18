from sqlalchemy import Column, ForeignKey, Integer, Unicode

from app.database import Base


class ProgramSubject(Base):
    __tablename__ = "ChuongTrinh_MonHoc"

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


class ProgramSubjectPrerequisite(Base):
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


class ProgramSession(Base):
    __tablename__ = "BuoiHoc"

    BuoiHocId = Column(Integer, primary_key=True, autoincrement=True)
    ChuongTrinhMonHocId = Column(
        Integer,
        ForeignKey("ChuongTrinh_MonHoc.ChuongTrinhMonHocId"),
        nullable=False,
    )
    SoThuTu = Column(Integer, nullable=False)
    ChuDe = Column(Unicode(200), nullable=False)
    MucTieu = Column(Unicode(1000), nullable=True)
