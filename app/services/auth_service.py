from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from app.schemas.nguoi_dung import (
    NguoiDungCreate,
    NguoiDungLock
)

from app.models.nguoi_dung import NguoiDung
from app.models.revoked_token import RevokedToken
from app.models.token_mat_khau import TokenMatKhau

from app.schemas.login import LoginRequest
from app.schemas.register import RegisterRequest
from app.schemas.forgot_password import ForgotPasswordRequest
from app.schemas.reset_password import ResetPasswordRequest

from app.services.email_service import (
    send_reset_password_email
)

from app.core.security import (
    create_access_token,
    decode_access_token
)

from datetime import (
    datetime,
    timedelta,
    timezone
)

import hashlib
import secrets
import jwt



# ============================================================
# PASSWORD HASH
# ============================================================

password_hash = PasswordHash.recommended()



# ============================================================
# ĐĂNG KÝ USER
# ============================================================

def register_user(
    db: Session,
    request: RegisterRequest
):

    email = str(
        request.email
    ).strip().lower()


    ho_ten = request.ho_ten.strip()


    so_dien_thoai = (
        request.so_dien_thoai.strip()
        if request.so_dien_thoai
        else None
    )


    existing_user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.Email == email
        )
        .first()
    )


    if existing_user:

        raise HTTPException(
            status_code=400,
            detail="Email đã được sử dụng"
        )



    new_user = NguoiDung(

        HoTen=ho_ten,

        Email=email,

        SoDienThoai=so_dien_thoai,

        MatKhauHash=password_hash.hash(
            request.password
        ),

        TrangThai="HoatDong",

        SoLanDangNhapSai=0,

        KhoaDen=None,

        LyDoKhoa=None,

        NgayTao=datetime.now(),

        NgayCapNhat=datetime.now()

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



    return {

        "message":
            "Đăng ký thành công",

        "user": {

            "nguoiDungId":
                new_user.NguoiDungId,

            "hoTen":
                new_user.HoTen,

            "email":
                new_user.Email,

            "trangThai":
                new_user.TrangThai

        }

    }




# ============================================================
# ADMIN TẠO USER
# ============================================================

def create_user(
    db: Session,
    request: NguoiDungCreate
):

    email = str(
        request.email
    ).strip().lower()



    exists = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.Email == email
        )
        .first()
    )


    if exists:

        raise HTTPException(
            status_code=400,
            detail="Email đã được sử dụng"
        )



    user = NguoiDung(

        HoTen=request.ho_ten.strip(),

        Email=email,

        SoDienThoai=request.so_dien_thoai,

        MatKhauHash=password_hash.hash(
            request.password
        ),

        TrangThai="HoatDong",

        SoLanDangNhapSai=0,

        KhoaDen=None,

        LyDoKhoa=None,

        TokenValidAfter=None,

        NgayTao=datetime.now(),

        NgayCapNhat=datetime.now()

    )



    try:

        db.add(user)

        db.commit()

        db.refresh(user)


    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể tạo người dùng"
        )



    return {

        "message":
            "Tạo người dùng thành công",

        "user": {

            "nguoiDungId":
                user.NguoiDungId,

            "hoTen":
                user.HoTen,

            "email":
                user.Email,

            "trangThai":
                user.TrangThai

        }

    }




# ============================================================
# ĐĂNG NHẬP
# ============================================================

def login_user(
    db: Session,
    request: LoginRequest
):

    email = str(
        request.email
    ).strip().lower()



    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.Email == email
        )
        .first()
    )



    if not user:

        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng"
        )



    now = datetime.now()



    # ========================================================
    # KIỂM TRA KHÓA ADMIN
    # ========================================================

    if user.TrangThai == "BiKhoa":

        raise HTTPException(
            status_code=423,
            detail=(
                "Tài khoản đã bị khóa"
                +
                (
                    f": {user.LyDoKhoa}"
                    if user.LyDoKhoa
                    else ""
                )
            )
        )



    # ========================================================
    # KIỂM TRA KHÓA TẠM THỜI
    # ========================================================

    if (
        user.KhoaDen
        and user.KhoaDen > now
    ):

        raise HTTPException(
            status_code=423,
            detail="Tài khoản đang bị khóa tạm thời"
        )



    # ========================================================
    # HẾT HẠN KHÓA -> MỞ LẠI
    # ========================================================

    if (
        user.KhoaDen
        and user.KhoaDen <= now
    ):

        user.KhoaDen = None

        user.SoLanDangNhapSai = 0

        user.TrangThai = "HoatDong"

        user.LyDoKhoa = None



    # ========================================================
    # KIỂM TRA PASSWORD
    # ========================================================

    try:

        password_correct = password_hash.verify(
            request.password,
            user.MatKhauHash
        )

    except Exception:

        password_correct = False



    if not password_correct:


        if user.SoLanDangNhapSai is None:

            user.SoLanDangNhapSai = 0



        user.SoLanDangNhapSai += 1



        if user.SoLanDangNhapSai >= 5:


            user.KhoaDen = (
                now + timedelta(minutes=15)
            )


            user.TrangThai = "KhoaTamThoi"


            user.LyDoKhoa = (
                "Sai mật khẩu 5 lần liên tiếp"
            )



        db.commit()



        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng"
        )



    # ========================================================
    # LOGIN THÀNH CÔNG
    # ========================================================


    user.SoLanDangNhapSai = 0

    user.KhoaDen = None

    user.LyDoKhoa = None

    user.NgayCapNhat = now



    db.commit()

    db.refresh(user)



    token = create_access_token(

        {

            "sub":
                user.Email,

            "user_id":
                user.NguoiDungId

        }

    )



    return {

        "message":
            "Đăng nhập thành công",

        "access_token":
            token,

        "token_type":
            "bearer",

        "nguoiDungId":
            user.NguoiDungId,

        "hoTen":
            user.HoTen,

        "email":
            user.Email

    }
# ============================================================
# ĐĂNG XUẤT
# ============================================================

def logout_user(
    db: Session,
    token: str
):

    try:

        payload = decode_access_token(
            token
        )


    except jwt.ExpiredSignatureError:

        raise HTTPException(
            status_code=401,
            detail="Phiên đăng nhập đã hết hạn"
        )


    except jwt.InvalidTokenError:

        raise HTTPException(
            status_code=401,
            detail="Token không hợp lệ"
        )



    jti = payload.get("jti")

    exp = payload.get("exp")



    if not jti or not exp:

        raise HTTPException(
            status_code=401,
            detail="Token không hợp lệ"
        )



    exists = (
        db.query(RevokedToken)
        .filter(
            RevokedToken.Jti == jti
        )
        .first()
    )



    if exists:

        return {
            "message":
                "Đăng xuất thành công"
        }



    revoked = RevokedToken(

        Jti=jti,

        ExpiresAt=datetime.fromtimestamp(
            exp,
            tz=timezone.utc
        ).replace(
            tzinfo=None
        )

    )


    try:

        db.add(revoked)

        db.commit()


    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể đăng xuất"
        )



    return {

        "message":
            "Đăng xuất thành công"

    }




# ============================================================
# ĐỔI MẬT KHẨU
# ============================================================

def update_password(
    db: Session,
    user: NguoiDung,
    current_password: str,
    new_password: str
):

    try:

        correct = password_hash.verify(
            current_password,
            user.MatKhauHash
        )


    except Exception:

        correct = False



    if not correct:

        raise HTTPException(
            status_code=400,
            detail="Mật khẩu hiện tại không đúng"
        )



    now = datetime.now()



    user.MatKhauHash = password_hash.hash(
        new_password
    )


    user.NgayCapNhat = now



    # Thu hồi JWT cũ

    user.TokenValidAfter = now



    try:

        db.commit()

        db.refresh(user)


    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể cập nhật mật khẩu"
        )



    return {

        "message":
            "Cập nhật mật khẩu thành công"

    }




# ============================================================
# QUÊN MẬT KHẨU
# ============================================================

def forgot_password(
    db: Session,
    request: ForgotPasswordRequest
):

    email = str(
        request.email
    ).strip().lower()



    message = (
        "Nếu email tồn tại trong hệ thống, "
        "hướng dẫn đặt lại mật khẩu đã được gửi."
    )



    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.Email == email
        )
        .first()
    )



    if not user:

        return {
            "message":
                message
        }



    raw_token = secrets.token_urlsafe(32)



    token_hash = hashlib.sha256(
        raw_token.encode()
    ).hexdigest()



    now = datetime.now()



    reset_token = TokenMatKhau(

        NguoiDungId=user.NguoiDungId,

        Token=token_hash,

        ThoiGianTao=now,

        ThoiGianHetHan=
            now + timedelta(minutes=30),

        DaSuDung=False

    )



    try:

        db.add(reset_token)

        db.commit()


    except Exception:

        db.rollback()

        return {
            "message":
                message
        }



    reset_link = (

        "http://localhost:5173/reset-password"

        f"?token={raw_token}"

    )



    try:

        send_reset_password_email(

            recipient_email=user.Email,

            reset_link=reset_link

        )


    except Exception:

        pass



    return {

        "message":
            message

    }




# ============================================================
# RESET PASSWORD
# ============================================================

def reset_password(
    db: Session,
    request: ResetPasswordRequest
):

    token_hash = hashlib.sha256(
        request.token.encode()
    ).hexdigest()



    reset_token = (

        db.query(TokenMatKhau)

        .filter(

            TokenMatKhau.Token == token_hash,

            TokenMatKhau.DaSuDung == False

        )

        .first()

    )



    if not reset_token:

        raise HTTPException(
            status_code=400,
            detail="Token không hợp lệ"
        )



    now = datetime.now()



    if reset_token.ThoiGianHetHan < now:


        reset_token.DaSuDung = True

        db.commit()


        raise HTTPException(
            status_code=400,
            detail="Token đã hết hạn"
        )



    user = (

        db.query(NguoiDung)

        .filter(

            NguoiDung.NguoiDungId
            ==
            reset_token.NguoiDungId

        )

        .first()

    )



    if not user:

        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng"
        )



    user.MatKhauHash = password_hash.hash(

        request.new_password

    )



    # Thu hồi JWT cũ

    user.TokenValidAfter = now



    user.NgayCapNhat = now



    reset_token.DaSuDung = True



    try:

        db.commit()


    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể đặt lại mật khẩu"
        )



    return {

        "message":
            "Đặt lại mật khẩu thành công"

    }




# ============================================================
# CẬP NHẬT USER
# ============================================================

def update_user(
    db: Session,
    user_id: int,
    request
):

    user = (

        db.query(NguoiDung)

        .filter(

            NguoiDung.NguoiDungId
            ==
            user_id

        )

        .first()

    )



    if not user:

        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng"
        )



    if request.email:


        email = str(
            request.email
        ).strip().lower()



        exists = (

            db.query(NguoiDung)

            .filter(

                NguoiDung.Email == email,

                NguoiDung.NguoiDungId != user_id

            )

            .first()

        )



        if exists:

            raise HTTPException(
                status_code=400,
                detail="Email đã tồn tại"
            )



        user.Email = email



    if request.ho_ten:

        user.HoTen = request.ho_ten.strip()



    if request.so_dien_thoai:

        user.SoDienThoai = (
            request.so_dien_thoai.strip()
        )



    user.NgayCapNhat = datetime.now()



    try:

        db.commit()

        db.refresh(user)


    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể cập nhật"
        )



    return {

        "message":
            "Cập nhật thành công"

    }




# ============================================================
# KHÓA TÀI KHOẢN
# ============================================================

def lock_user(
    db: Session,
    user_id: int,
    request: NguoiDungLock
):


    user = (

        db.query(NguoiDung)

        .filter(

            NguoiDung.NguoiDungId
            ==
            user_id

        )

        .first()

    )



    if not user:

        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng"
        )



    user.TrangThai = "BiKhoa"



    user.KhoaDen = None



    user.LyDoKhoa = (

        request.ly_do_khoa.strip()

        if request.ly_do_khoa

        else

        "Bị khóa bởi quản trị viên"

    )



    # Vô hiệu hóa toàn bộ JWT cũ

    user.TokenValidAfter = datetime.now()



    user.NgayCapNhat = datetime.now()



    try:

        db.commit()

        db.refresh(user)


    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể khóa tài khoản"
        )



    return {

        "message":
            "Khóa tài khoản thành công",

        "nguoiDungId":
            user.NguoiDungId,

        "trangThai":
            user.TrangThai,

        "lyDoKhoa":
            user.LyDoKhoa

    }

# ============================================================
# MỞ KHÓA TÀI KHOẢN NGƯỜI DÙNG
# ============================================================

def unlock_user(
    db: Session,
    user_id: int
):
    # --------------------------------------------------------
    # Tìm người dùng
    # --------------------------------------------------------

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId == user_id
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng"
        )

    # --------------------------------------------------------
    # Kiểm tra tài khoản có đang bị khóa không
    # --------------------------------------------------------

    if user.TrangThai != "BiKhoa":
        raise HTTPException(
            status_code=400,
            detail="Tài khoản chưa bị khóa"
        )

    # --------------------------------------------------------
    # Mở khóa tài khoản
    # --------------------------------------------------------

    user.TrangThai = "HoatDong"
    user.KhoaDen = None
    user.LyDoKhoa = None
    user.SoLanDangNhapSai = 0

    # --------------------------------------------------------
    # Thu hồi token cũ
    # Người dùng phải đăng nhập lại
    # --------------------------------------------------------

    user.TokenValidAfter = datetime.now()
    user.NgayCapNhat = datetime.now()

    # --------------------------------------------------------
    # Lưu database
    # --------------------------------------------------------

    try:
        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Không thể mở khóa tài khoản"
        )

    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return {
        "message": "Mở khóa tài khoản thành công",
        "user": {
            "nguoiDungId": user.NguoiDungId,
            "hoTen": user.HoTen,
            "email": user.Email,
            "trangThai": user.TrangThai,
            "ngayCapNhat": user.NgayCapNhat
        }
    }