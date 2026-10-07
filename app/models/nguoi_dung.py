from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
)
from sqlalchemy.orm import synonym

from app.database import Base


class NguoiDung(Base):
    __tablename__ = "NguoiDung"

    # =========================================================
    # KHÓA CHÍNH
    # =========================================================

    NguoiDungId = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    # =========================================================
    # THÔNG TIN CƠ BẢN
    # =========================================================

    HoTen = Column(
        String(100),
        nullable=False
    )

    Email = Column(
        String(255),
        nullable=False,
        unique=True
    )

    SoDienThoai = Column(
        String(20),
        nullable=True
    )

    # =========================================================
    # MẬT KHẨU
    # =========================================================

    # Chỉ lưu mật khẩu đã hash.
    # Không lưu mật khẩu dạng plain text.

    MatKhauHash = Column(
        String(255),
        nullable=False
    )

    # =========================================================
    # TRẠNG THÁI TÀI KHOẢN
    # =========================================================

    TrangThai = Column(
        String(50),
        nullable=False
    )

    # =========================================================
    # KÍCH HOẠT TÀI KHOẢN
    # =========================================================

    DaKichHoat = Column(
        Boolean,
        nullable=False,
        default=True
    )

    # =========================================================
    # MẬT KHẨU TẠM THỜI
    # =========================================================

    # Cột thực tế trong database:
    # BatBuocDoiMatKhau
    #
    # True  = tài khoản bắt buộc đổi mật khẩu
    # False = không bắt buộc đổi mật khẩu

    BatBuocDoiMatKhau = Column(
        Boolean,
        nullable=False,
        default=False
    )

    # Cột thực tế trong database:
    # CanDoiMatKhau
    #
    # True  = người dùng đang cần đổi mật khẩu
    # False = người dùng không cần đổi mật khẩu

    CanDoiMatKhau = Column(
        Boolean,
        nullable=False,
        default=False
    )

    # Tên nghiệp vụ dùng trong code.
    # Không tạo thêm cột database.
    #
    # YeuCauDoiMatKhau -> CanDoiMatKhau

    YeuCauDoiMatKhau = synonym(
        "CanDoiMatKhau"
    )

    # =========================================================
    # HẾT HẠN MẬT KHẨU TẠM THỜI
    # =========================================================

    # Thời điểm mật khẩu tạm thời hết hạn.
    #
    # NULL = tài khoản không có thời hạn mật khẩu tạm
    # hoặc không sử dụng mật khẩu tạm thời.

    MatKhauTamThoiHetHan = Column(
        DateTime,
        nullable=True
    )

    # =========================================================
    # BẢO VỆ ĐĂNG NHẬP
    # =========================================================

    # Số lần đăng nhập sai liên tiếp

    SoLanDangNhapSai = Column(
        Integer,
        nullable=False,
        default=0
    )

    # Thời điểm tài khoản được mở khóa

    KhoaDen = Column(
        DateTime,
        nullable=True
    )

    # Lý do khóa tài khoản

    LyDoKhoa = Column(
        String(255),
        nullable=True
    )

    # =========================================================
    # THỜI GIAN
    # =========================================================

    NgayTao = Column(
        DateTime,
        nullable=True
    )

    NgayCapNhat = Column(
        DateTime,
        nullable=True
    )

    # =========================================================
    # JWT TOKEN
    # =========================================================

    # Khi đổi mật khẩu hoặc cần vô hiệu hóa
    # các token cũ, TokenValidAfter được cập nhật.

    TokenValidAfter = Column(
        DateTime,
        nullable=True
    )