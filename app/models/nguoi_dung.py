
from sqlalchemy import (
    Column,
    Integer,
    String,
    Unicode,
    DateTime,
    Boolean,
    Date,
)
from sqlalchemy.orm import synonym

from app.database import Base


class NguoiDung(Base):
    __tablename__ = "NguoiDung"

    # KHOA CHINH
    NguoiDungId = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # THONG TIN CO BAN
    HoTen = Column(
        Unicode(100),
        nullable=False,
    )

    Email = Column(
        String(255),
        nullable=False,
        unique=True,
    )

    SoDienThoai = Column(String(20), nullable=True)
    NgaySinh = Column(Date, nullable=True)
    DiaChi = Column(Unicode(255), nullable=True)
    TrinhDoDauVao = Column(Unicode(150), nullable=True)
    GhiChuHoSo = Column(Unicode(2000), nullable=True)

    # MAT KHAU
    # Chi luu mat khau da hash.
    MatKhauHash = Column(
        String(255),
        nullable=False,
    )

    # TRANG THAI TAI KHOAN
    TrangThai = Column(
        String(50),
        nullable=False,
    )

    # KICH HOAT TAI KHOAN
    DaKichHoat = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    # DOI MAT KHAU
    BatBuocDoiMatKhau = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    CanDoiMatKhau = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Ten nghiep vu dung trong code, khong tao cot moi.
    YeuCauDoiMatKhau = synonym("CanDoiMatKhau")

    # HAN MAT KHAU TAM THOI
    MatKhauTamThoiHetHan = Column(
        DateTime,
        nullable=True,
    )

    # BAO VE DANG NHAP
    SoLanDangNhapSai = Column(
        Integer,
        nullable=False,
        default=0,
    )

    KhoaDen = Column(
        DateTime,
        nullable=True,
    )

    LyDoKhoa = Column(
        String(255),
        nullable=True,
    )

    # THOI GIAN
    NgayTao = Column(
        DateTime,
        nullable=True,
    )

    NgayCapNhat = Column(
        DateTime,
        nullable=True,
    )

    # JWT TOKEN
    # Token cap truoc thoi diem nay co the bi vo hieu hoa.
    TokenValidAfter = Column(
        DateTime,
        nullable=True,
    )
