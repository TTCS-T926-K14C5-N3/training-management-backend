from datetime import datetime

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Unicode, UnicodeText, UniqueConstraint

from app.database import Base


class AttendanceRecord(Base):
    __tablename__ = "DiemDanhTheoNgay"
    __table_args__ = (
        UniqueConstraint(
            "LopHocId",
            "HocVienId",
            "NgayHoc",
            name="UQ_DiemDanhTheoNgay_Lop_HocVien_Ngay",
        ),
        CheckConstraint(
            "TrangThai IN ('present', 'late', 'excused_absence', 'unexcused_absence')",
            name="CK_DiemDanhTheoNgay_TrangThai",
        ),
    )

    DiemDanhId = Column(Integer, primary_key=True, autoincrement=True)
    LopHocId = Column(Integer, ForeignKey("LopHoc.LopHocId"), nullable=False)
    HocVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    NgayHoc = Column(Date, nullable=False)
    TrangThai = Column(Unicode(30), nullable=False)
    GhiChu = Column(UnicodeText, nullable=True)
    NguoiCapNhatId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    NgayCapNhat = Column(DateTime, nullable=False, default=datetime.now)


class AbsenceRequest(Base):
    __tablename__ = "DonXinVang"
    __table_args__ = (
        CheckConstraint("TrangThai IN ('pending', 'approved', 'rejected')", name="CK_DonXinVang_TrangThai"),
    )

    DonXinVangId = Column(Integer, primary_key=True, autoincrement=True)
    LopHocId = Column(Integer, ForeignKey("LopHoc.LopHocId"), nullable=False)
    HocVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    NgayHoc = Column(Date, nullable=False)
    LyDo = Column(Unicode(2000), nullable=False)
    TepChungMinh = Column(Unicode(1000), nullable=True)
    TrangThai = Column(Unicode(20), nullable=False, default="pending")
    LyDoXuLy = Column(Unicode(1000), nullable=True)
    NguoiXuLyId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=True)
    NgayXuLy = Column(DateTime, nullable=True)
    NgayTao = Column(DateTime, nullable=False, default=datetime.now)


class AttendanceAudit(Base):
    __tablename__ = "DiemDanhTheoNgay_LichSu"

    LichSuId = Column(Integer, primary_key=True, autoincrement=True)
    DoiTuong = Column(Unicode(30), nullable=False)
    DoiTuongId = Column(Integer, nullable=False)
    HanhDong = Column(Unicode(30), nullable=False)
    DuLieuCu = Column(UnicodeText, nullable=True)
    DuLieuMoi = Column(UnicodeText, nullable=True)
    LyDo = Column(Unicode(1000), nullable=True)
    ThoiDiem = Column(DateTime, nullable=False, default=datetime.now)
    NguoiThucHienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)


class AbsenceThreshold(Base):
    __tablename__ = "NguongVang"
    __table_args__ = (
        CheckConstraint("TiLeToiDa >= 0 AND TiLeToiDa <= 100", name="CK_NguongVang_TiLe"),
    )

    ChuongTrinhId = Column(Integer, ForeignKey("ChuongTrinhDaoTao.ChuongTrinhId"), primary_key=True)
    TiLeToiDa = Column(Integer, nullable=False, default=20)
    NguoiCapNhatId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=True)
    NgayCapNhat = Column(DateTime, nullable=False, default=datetime.now)


class AttendanceNotification(Base):
    __tablename__ = "ThongBaoDiemDanh"

    ThongBaoId = Column(Integer, primary_key=True, autoincrement=True)
    NguoiNhanId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    HocVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=True)
    ChuongTrinhId = Column(Integer, ForeignKey("ChuongTrinhDaoTao.ChuongTrinhId"), nullable=True)
    Loai = Column(Unicode(40), nullable=False)
    TieuDe = Column(Unicode(200), nullable=False)
    NoiDung = Column(Unicode(1000), nullable=False)
    ThoiDiem = Column(DateTime, nullable=False, default=datetime.now)
    DaDoc = Column(DateTime, nullable=True)
