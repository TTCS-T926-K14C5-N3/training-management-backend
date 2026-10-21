from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Unicode,
    UnicodeText,
    UniqueConstraint,
)

from app.database import Base


class AbsenceRequest(Base):
    __tablename__ = "DonXinPhepVang"
    __table_args__ = (
        UniqueConstraint(
            "LichHocId",
            "HocVienId",
            name="UQ_DonXinPhepVang_LichHoc_HocVien",
        ),
    )

    RequestId = Column(Integer, primary_key=True, autoincrement=True)
    LichHocId = Column(
        Integer,
        ForeignKey("LichHoc.LichHocId"),
        nullable=False,
        index=True,
    )
    HocVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
        index=True,
    )
    LyDo = Column(Unicode(1000), nullable=False)
    TepMinhChungPath = Column(Unicode(500), nullable=True)
    TepMinhChungTen = Column(Unicode(255), nullable=True)
    TepMinhChungMime = Column(Unicode(100), nullable=True)
    TepMinhChungKichThuoc = Column(Integer, nullable=True)
    TrangThai = Column(Unicode(20), nullable=False, default="Chờ duyệt")
    LyDoDuyet = Column(Unicode(1000), nullable=True)
    NguoiDuyetId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=True,
    )
    ThoiDiemDuyet = Column(DateTime, nullable=True)
    NgayTao = Column(DateTime, nullable=False)


class AttendanceAudit(Base):
    __tablename__ = "DiemDanh_BuoiHoc_XinPhep_LichSu"

    AuditId = Column(Integer, primary_key=True, autoincrement=True)
    LichHocId = Column(
        Integer,
        ForeignKey("LichHoc.LichHocId"),
        nullable=False,
        index=True,
    )
    HocVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    TrangThaiCu = Column(Unicode(30), nullable=True)
    TrangThaiMoi = Column(Unicode(30), nullable=False)
    GhiChu = Column(Unicode(1000), nullable=True)
    NguoiThucHienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    ThoiDiem = Column(DateTime, nullable=False)


class AttendanceNotification(Base):
    __tablename__ = "DiemDanh_ThongBao"

    NotificationId = Column(Integer, primary_key=True, autoincrement=True)
    RequestId = Column(
        Integer,
        ForeignKey("DonXinPhepVang.RequestId"),
        nullable=False,
        index=True,
    )
    NguoiNhanId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
        index=True,
    )
    NoiDung = Column(UnicodeText, nullable=False)
    ThoiDiem = Column(DateTime, nullable=False)
    DaDoc = Column(Boolean, nullable=False, default=False)
