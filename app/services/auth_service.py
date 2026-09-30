from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from app.models.nguoi_dung import NguoiDung
from app.schemas.login import LoginRequest
from app.schemas.register import RegisterRequest
from app.database import get_db
from fastapi import HTTPException, Depends, status

# PASSWORD HASH
password_hash = PasswordHash.recommended()


# ĐĂNG KÝ
def register_user(
    db: Session,
    request: RegisterRequest
):
    # Chuẩn hóa dữ liệu
    email = str(request.email).strip().lower()
    ho_ten = request.ho_ten.strip()

    so_dien_thoai = (
        request.so_dien_thoai.strip()
        if request.so_dien_thoai
        else None
    )

   
    # Kiểm tra email đã tồn tại
    existing_user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email đã được sử dụng"
        )

    # Hash mật khẩu

    hashed_password = password_hash.hash(
        request.password
    )

    now = datetime.now()

    # Tạo người dùng

    new_user = NguoiDung(
        HoTen=ho_ten,
        Email=email,
        SoDienThoai=so_dien_thoai,
        MatKhauHash=hashed_password,
        TrangThai="HoatDong",
        SoLanDangNhapSai=0,
        KhoaDen=None,
        LyDoKhoa=None,
        NgayTao=now,
        NgayCapNhat=now
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể tạo tài khoản"
        )

    # Không trả MatKhauHash ra ngoài
    return {
        "message": "Đăng ký thành công",
        "user": {
            "nguoiDungId": new_user.NguoiDungId,
            "hoTen": new_user.HoTen,
            "email": new_user.Email,
            "soDienThoai": new_user.SoDienThoai,
            "trangThai": new_user.TrangThai
        }
    }


# ĐĂNG NHẬP

def login_user(
    db: Session,
    request: LoginRequest
):
    email = str(request.email).strip().lower()

    # Tìm người dùng theo email
 
    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    # Không tiết lộ email có tồn tại hay không
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng"
        )

    now = datetime.now()


    # Kiểm tra tài khoản đang bị khóa

    if user.KhoaDen and user.KhoaDen > now:
        raise HTTPException(
            status_code=423,
            detail="Tài khoản đang bị khóa, vui lòng thử lại sau"
        )

    # Nếu hết thời gian khóa -> mở khóa

    if user.KhoaDen and user.KhoaDen <= now:
        user.KhoaDen = None
        user.SoLanDangNhapSai = 0
        user.TrangThai = "HoatDong"
        user.LyDoKhoa = None
        user.NgayCapNhat = now

        db.commit()
        db.refresh(user)

    # Kiểm tra mật khẩu

    try:
        password_correct = password_hash.verify(
            request.password,
            user.MatKhauHash
        )

    except Exception:
        password_correct = False

    # Mật khẩu sai
    if not password_correct:

        if user.SoLanDangNhapSai is None:
            user.SoLanDangNhapSai = 0

        user.SoLanDangNhapSai += 1
        user.NgayCapNhat = now

        # Sai 5 lần -> khóa 15 phút
        if user.SoLanDangNhapSai >= 5:
            user.KhoaDen = (
                now + timedelta(minutes=15)
            )

            user.TrangThai = "BiKhoa"

            user.LyDoKhoa = (
                "Sai mật khẩu 5 lần liên tiếp"
            )

        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng"
        )

    # Đăng nhập thành công

    user.SoLanDangNhapSai = 0
    user.KhoaDen = None
    user.TrangThai = "HoatDong"
    user.LyDoKhoa = None
    user.NgayCapNhat = now

    # Lấy vai trò của người dùng

    role_query = text("""
        SELECT
            vt.VaiTroId,
            vt.TenVaiTro
        FROM VaiTro vt

        INNER JOIN NguoiDung_VaiTro ndvt
            ON vt.VaiTroId = ndvt.VaiTroId

        WHERE ndvt.NguoiDungId = :nguoi_dung_id
    """)

    roles = db.execute(
        role_query,
        {
            "nguoi_dung_id":
                user.NguoiDungId
        }
    ).mappings().all()

    db.commit()
    db.refresh(user)

    # Response

    return {
        "message": "Đăng nhập thành công",

        "nguoiDungId":
            user.NguoiDungId,

        "hoTen":
            user.HoTen,

        "email":
            user.Email,

        "vaiTro": [
            {
                "vaiTroId":
                    role["VaiTroId"],

                "tenVaiTro":
                    role["TenVaiTro"]
            }

            for role in roles
        ]
    }
# HÀM GIẢ LẬP LẤY USER (Dùng tạm để test Phân quyền khi chưa có tính năng JWT)
def get_current_user(db: Session = Depends(get_db)):
    # Tạm thời gán cứng User ID = 1 đang đăng nhập (bạn có thể đổi thành ID thực tế trong SQL của bạn)
    user_id_dang_test = 1
    
    user = db.query(NguoiDung).filter(NguoiDung.NguoiDungId == user_id_dang_test).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Tài khoản test không tồn tại trong Database"
        )
    return user

# CHỐT CHẶN PHÂN QUYỀN (SCRUM-64)
def get_current_admin(
    current_user: NguoiDung = Depends(get_current_user), # Hàm giải mã token lấy ra User hiện tại
    db: Session = Depends(get_db) # Hàm kết nối Database
):
    """
    Kiểm tra: Chỉ cho phép tài khoản có quyền 'admin' đi qua
    """
    # Sử dụng lại logic truy vấn bảng quyền giống hệt như lúc Đăng nhập
    role_query = text("""
        SELECT vt.TenVaiTro 
        FROM VaiTro vt
        INNER JOIN NguoiDung_VaiTro ndvt ON vt.VaiTroId = ndvt.VaiTroId
        WHERE ndvt.NguoiDungId = :nguoi_dung_id
    """)

    roles = db.execute(
        role_query, 
        {"nguoi_dung_id": current_user.NguoiDungId}
    ).mappings().all()

    # Chuyển kết quả thành danh sách các tên quyền (chuyển về chữ thường để dễ so sánh)
    danh_sach_quyen = [role["TenVaiTro"].lower() for role in roles]

    # Kiểm tra xem có quyền quản trị không
    # (Nếu trong SQL server bạn lưu là "Quản trị viên" thì thay chữ "admin" bên dưới thành "quản trị viên")
    if "admin" not in danh_sach_quyen:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Quyền truy cập bị từ chối! Tính năng này chỉ dành cho Quản trị viên."
        )

    return current_user

