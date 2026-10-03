from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from app.models.nguoi_dung import NguoiDung
from app.models.vai_tro import VaiTro
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro

from app.schemas.nguoi_dung import (
    NguoiDungCreate,
    NguoiDungUpdate,
    NguoiDungLock,
)

from app.schemas.login import LoginRequest

from app.core.security import (
    create_access_token,
    decode_access_token,
)


# ============================================================
# PASSWORD HASHER
# ============================================================

ph = PasswordHasher()


# ============================================================
# HELPER
# ============================================================

def utc_now() -> datetime:
    """
    Lấy thời gian UTC hiện tại.
    """
    return datetime.utcnow()


def _commit_or_raise(db: Session, action: str = "Thao tác") -> None:
    """
    Commit transaction.
    Nếu có lỗi DB thì rollback và trả về HTTP 500.
    """
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{action} thất bại",
        )


def _user_summary(user: NguoiDung) -> Dict[str, Any]:
    """
    Chuẩn hóa thông tin user trả về.
    """
    roles = (
        [
            {
                "VaiTroId": item.vaitro.VaiTroId,
                "TenVaiTro": item.vaitro.TenVaiTro,
            }
            for item in user.nguoi_dung_vai_tro
            if item.vaitro
        ]
        if hasattr(user, "nguoi_dung_vai_tro")
        else []
    )

    return {
        "NguoiDungId": user.NguoiDungId,
        "HoTen": user.HoTen,
        "Email": user.Email,
        "SoDienThoai": user.SoDienThoai,
        "TrangThai": user.TrangThai,
        "SoLanDangNhapSai": user.SoLanDangNhapSai,
        "KhoaDen": user.KhoaDen,
        "LyDoKhoa": user.LyDoKhoa,
        "roles": roles,
    }


# ============================================================
# REGISTER USER
# ============================================================

def register_user(
    db: Session,
    request: NguoiDungCreate,
) -> Dict[str, Any]:
    """
    Đăng ký tài khoản người dùng.
    """

    # Kiểm tra email đã tồn tại
    existing_user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == request.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email đã được sử dụng",
        )

    # Kiểm tra số điện thoại nếu có
    if getattr(request, "SoDienThoai", None):
        existing_phone = (
            db.query(NguoiDung)
            .filter(NguoiDung.SoDienThoai == request.SoDienThoai)
            .first()
        )

        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Số điện thoại đã được sử dụng",
            )

    # Hash password
    password_hash = ph.hash(request.password)

    now = utc_now()

    user = NguoiDung(
        HoTen=request.HoTen,
        Email=request.email,
        SoDienThoai=getattr(request, "SoDienThoai", None),
        MatKhauHash=password_hash,
        TrangThai="HoatDong",
        SoLanDangNhapSai=0,
        KhoaDen=None,
        LyDoKhoa=None,
        NgayTao=now,
        NgayCapNhat=now,
    )

    db.add(user)

    try:
        db.flush()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể tạo tài khoản",
        )

    # Gán role mặc định nếu tồn tại
    default_role = (
        db.query(VaiTro)
        .filter(VaiTro.TenVaiTro == "user")
        .first()
    )

    if default_role:
        user_role = NguoiDungVaiTro(
            NguoiDungId=user.NguoiDungId,
            VaiTroId=default_role.VaiTroId,
        )

        db.add(user_role)

    _commit_or_raise(db, "Đăng ký tài khoản")

    db.refresh(user)

    return {
        "message": "Đăng ký tài khoản thành công",
        "user": _user_summary(user),
    }


# ============================================================
# CREATE USER - ADMIN
# ============================================================

def create_user(
    db: Session,
    request: NguoiDungCreate,
) -> Dict[str, Any]:
    """
    Admin tạo tài khoản người dùng.
    """

    # Kiểm tra email
    existing_user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == request.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email đã được sử dụng",
        )

    # Kiểm tra số điện thoại
    if getattr(request, "SoDienThoai", None):
        existing_phone = (
            db.query(NguoiDung)
            .filter(NguoiDung.SoDienThoai == request.SoDienThoai)
            .first()
        )

        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Số điện thoại đã được sử dụng",
            )

    # Hash password
    password_hash = ph.hash(request.password)

    now = utc_now()

    user = NguoiDung(
        HoTen=request.HoTen,
        Email=request.email,
        SoDienThoai=getattr(request, "SoDienThoai", None),
        MatKhauHash=password_hash,
        TrangThai="HoatDong",
        SoLanDangNhapSai=0,
        KhoaDen=None,
        LyDoKhoa=None,
        NgayTao=now,
        NgayCapNhat=now,
    )

    db.add(user)

    try:
        db.flush()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Không thể tạo tài khoản",
        )

    # Role mặc định
    default_role = (
        db.query(VaiTro)
        .filter(VaiTro.TenVaiTro == "user")
        .first()
    )

    if default_role:
        user_role = NguoiDungVaiTro(
            NguoiDungId=user.NguoiDungId,
            VaiTroId=default_role.VaiTroId,
        )

        db.add(user_role)

    _commit_or_raise(db, "Tạo tài khoản")

    db.refresh(user)

    return {
        "message": "Tạo tài khoản thành công",
        "user": _user_summary(user),
    }
# ============================================================
# LOGIN USER
# ============================================================

def login_user(
    db: Session,
    request: LoginRequest,
) -> Dict[str, Any]:
    """
    Đăng nhập tài khoản.

    Quy tắc:
    - Kiểm tra email tồn tại.
    - Kiểm tra tài khoản có đang bị khóa hay không.
    - Xác thực mật khẩu bằng Argon2.
    - Sai mật khẩu 5 lần liên tiếp -> khóa 15 phút.
    - Đăng nhập thành công -> reset số lần sai.
    - Tạo access token.
    """

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == request.email)
        .first()
    )

    # Không tiết lộ tài khoản có tồn tại hay không
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác",
        )

    now = utc_now()

    # ========================================================
    # KIỂM TRA TRẠNG THÁI TÀI KHOẢN
    # ========================================================

    if user.TrangThai == "BiKhoa" and not user.KhoaDen:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                user.LyDoKhoa
                or "Tài khoản đã bị khóa"
            ),
        )

    # ========================================================
    # KIỂM TRA KHÓA TẠM THỜI
    # ========================================================

    if user.KhoaDen:
        if user.KhoaDen > now:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Tài khoản đang bị khóa tạm thời",
            )

        # Hết thời gian khóa -> tự động mở khóa
        user.KhoaDen = None
        user.SoLanDangNhapSai = 0
        user.TrangThai = "HoatDong"
        user.LyDoKhoa = None
        user.NgayCapNhat = now

        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể cập nhật trạng thái tài khoản",
            )

    # ========================================================
    # KIỂM TRA TRẠNG THÁI HOẠT ĐỘNG
    # ========================================================

    if user.TrangThai != "HoatDong":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản không ở trạng thái hoạt động",
        )

    # ========================================================
    # KIỂM TRA MẬT KHẨU
    # ========================================================

    try:
        password_valid = ph.verify(
            user.MatKhauHash,
            request.password,
        )

    except (VerifyMismatchError, VerificationError):
        password_valid = False

    # ========================================================
    # SAI MẬT KHẨU
    # ========================================================

    if not password_valid:

        user.SoLanDangNhapSai = (
            (user.SoLanDangNhapSai or 0) + 1
        )

        # Sai 5 lần -> khóa 15 phút
        if user.SoLanDangNhapSai >= 5:
            user.KhoaDen = now + timedelta(minutes=15)
            user.TrangThai = "BiKhoa"
            user.LyDoKhoa = "Sai mật khẩu 5 lần liên tiếp"
            user.NgayCapNhat = now

            try:
                db.commit()
            except SQLAlchemyError:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Không thể cập nhật trạng thái tài khoản",
                )

            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=(
                    "Tài khoản đã bị khóa tạm thời 15 phút "
                    "do nhập sai mật khẩu 5 lần liên tiếp"
                ),
            )

        user.NgayCapNhat = now

        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể cập nhật số lần đăng nhập sai",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác",
        )

    # ========================================================
    # ĐĂNG NHẬP THÀNH CÔNG
    # ========================================================

    user.SoLanDangNhapSai = 0
    user.KhoaDen = None
    user.LyDoKhoa = None
    user.TrangThai = "HoatDong"
    user.NgayCapNhat = now

    # ========================================================
    # LẤY ROLE
    # ========================================================

    roles = (
        [
            item.vaitro.TenVaiTro
            for item in user.nguoi_dung_vai_tro
            if item.vaitro
        ]
        if hasattr(user, "nguoi_dung_vai_tro")
        else []
    )

    # Role mặc định nếu không có
    if not roles:
        roles = ["user"]

    # ========================================================
    # TẠO ACCESS TOKEN
    # ========================================================

    token_data = {
        "sub": str(user.NguoiDungId),
        "email": user.Email,
        "roles": roles,
    }

    access_token = create_access_token(
        data=token_data
    )

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Đăng nhập thất bại",
        )

    return {
        "message": "Đăng nhập thành công",
        "access_token": access_token,
        "token_type": "bearer",
        "user": _user_summary(user),
    }
# ============================================================
# LOGOUT USER
# ============================================================

def logout_user(
    db: Session,
    token: str,
) -> Dict[str, Any]:
    """
    Đăng xuất người dùng.

    Token được decode để lấy thông tin người dùng.
    Nếu hệ thống có cơ chế TokenValidAfter thì có thể
    dùng thời điểm này để vô hiệu hóa các token cũ.
    """

    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết hạn",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ",
        )

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == int(user_id))
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng",
        )

    # Nếu model có trường TokenValidAfter thì cập nhật.
    if hasattr(user, "TokenValidAfter"):
        user.TokenValidAfter = utc_now()

    user.NgayCapNhat = utc_now()

    _commit_or_raise(db, "Đăng xuất")

    return {
        "message": "Đăng xuất thành công",
    }


# ============================================================
# UPDATE PASSWORD
# ============================================================

def update_password(
    db: Session,
    user_id: int,
    old_password: str,
    new_password: str,
) -> Dict[str, Any]:
    """
    Đổi mật khẩu khi người dùng đang đăng nhập.
    """

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng",
        )

    # Kiểm tra mật khẩu hiện tại
    try:
        password_valid = ph.verify(
            user.MatKhauHash,
            old_password,
        )

    except (VerifyMismatchError, VerificationError):
        password_valid = False

    if not password_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu hiện tại không chính xác",
        )

    # Không cho dùng lại mật khẩu cũ
    if old_password == new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mật khẩu mới phải khác mật khẩu hiện tại",
        )

    # Hash mật khẩu mới
    user.MatKhauHash = ph.hash(new_password)

    now = utc_now()
    user.NgayCapNhat = now

    # Đổi mật khẩu -> vô hiệu hóa các token cũ
    if hasattr(user, "TokenValidAfter"):
        user.TokenValidAfter = now

    _commit_or_raise(db, "Đổi mật khẩu")

    return {
        "message": "Đổi mật khẩu thành công",
    }


# ============================================================
# FORGOT PASSWORD
# ============================================================

def forgot_password(
    db: Session,
    email: str,
) -> Dict[str, Any]:
    """
    Xử lý yêu cầu quên mật khẩu.

    Không tiết lộ email có tồn tại trong hệ thống hay không.
    """

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == email)
        .first()
    )

    # Không tiết lộ tài khoản có tồn tại
    if not user:
        return {
            "message": (
                "Nếu email tồn tại trong hệ thống, "
                "hướng dẫn đặt lại mật khẩu sẽ được gửi đến email."
            )
        }

    # ========================================================
    # TẠO RESET TOKEN
    # ========================================================

    reset_token = create_access_token(
        data={
            "sub": str(user.NguoiDungId),
            "purpose": "reset_password",
        }
    )

    return {
        "message": (
            "Nếu email tồn tại trong hệ thống, "
            "hướng dẫn đặt lại mật khẩu sẽ được gửi đến email."
        ),
        "reset_token": reset_token,
    }


# ============================================================
# RESET PASSWORD
# ============================================================

def reset_password(
    db: Session,
    token: str,
    new_password: str,
) -> Dict[str, Any]:
    """
    Đặt lại mật khẩu bằng reset token.
    """

    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token đặt lại mật khẩu không hợp lệ hoặc đã hết hạn",
        )

    # Chỉ chấp nhận token dùng cho reset password
    if payload.get("purpose") != "reset_password":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ",
        )

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == int(user_id))
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng",
        )

    # ========================================================
    # HASH PASSWORD MỚI
    # ========================================================

    user.MatKhauHash = ph.hash(new_password)

    # Reset trạng thái đăng nhập sai
    user.SoLanDangNhapSai = 0
    user.KhoaDen = None
    user.LyDoKhoa = None
    user.TrangThai = "HoatDong"

    now = utc_now()
    user.NgayCapNhat = now

    # Vô hiệu hóa các token cũ
    if hasattr(user, "TokenValidAfter"):
        user.TokenValidAfter = now

    _commit_or_raise(db, "Đặt lại mật khẩu")

    return {
        "message": "Đặt lại mật khẩu thành công",
    }
# ============================================================
# UPDATE USER
# ============================================================

def update_user(
    db: Session,
    user_id: int,
    request: NguoiDungUpdate,
) -> Dict[str, Any]:
    """
    Cập nhật thông tin người dùng.
    """

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng",
        )

    # ========================================================
    # KIỂM TRA EMAIL
    # ========================================================

    if getattr(request, "Email", None):
        existing_email = (
            db.query(NguoiDung)
            .filter(
                NguoiDung.Email == request.email,
                NguoiDung.NguoiDungId != user_id,
            )
            .first()
        )

        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email đã được sử dụng",
            )

        user.Email = request.email

    # ========================================================
    # CẬP NHẬT HỌ TÊN
    # ========================================================

    if getattr(request, "HoTen", None) is not None:
        user.HoTen = request.HoTen

    # ========================================================
    # CẬP NHẬT SỐ ĐIỆN THOẠI
    # ========================================================

    if getattr(request, "SoDienThoai", None) is not None:
        existing_phone = (
            db.query(NguoiDung)
            .filter(
                NguoiDung.SoDienThoai == request.SoDienThoai,
                NguoiDung.NguoiDungId != user_id,
            )
            .first()
        )

        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Số điện thoại đã được sử dụng",
            )

        user.SoDienThoai = request.SoDienThoai

    # ========================================================
    # CẬP NHẬT TRẠNG THÁI
    # ========================================================

    if getattr(request, "TrangThai", None) is not None:
        user.TrangThai = request.TrangThai

    user.NgayCapNhat = utc_now()

    _commit_or_raise(db, "Cập nhật người dùng")

    db.refresh(user)

    return {
        "message": "Cập nhật người dùng thành công",
        "user": _user_summary(user),
    }


# ============================================================
# LOCK USER
# ============================================================

def lock_user(
    db: Session,
    user_id: int,
    request: Union[NguoiDungLock, str, None] = None,
    ly_do_khoa: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Khóa tài khoản người dùng.

    Có thể truyền lý do theo một trong hai dạng:
    - request.LyDoKhoa
    - ly_do_khoa
    - request là chuỗi lý do
    """

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng",
        )

    # ========================================================
    # LẤY LÝ DO KHÓA
    # ========================================================

    reason = ly_do_khoa

    if isinstance(request, str):
        reason = request

    elif request is not None:
        reason = getattr(
            request,
            "LyDoKhoa",
            None,
        ) or reason

    if not reason:
        reason = "Tài khoản bị quản trị viên khóa"

    # ========================================================
    # KHÓA TÀI KHOẢN
    # ========================================================

    now = utc_now()

    user.TrangThai = "BiKhoa"
    user.KhoaDen = None
    user.LyDoKhoa = reason
    user.NgayCapNhat = now

    # Vô hiệu hóa token hiện tại
    if hasattr(user, "TokenValidAfter"):
        user.TokenValidAfter = now

    _commit_or_raise(db, "Khóa tài khoản")

    db.refresh(user)

    return {
        "message": "Khóa tài khoản thành công",
        "user": _user_summary(user),
    }


# ============================================================
# UNLOCK USER
# ============================================================

def unlock_user(
    db: Session,
    user_id: int,
) -> Dict[str, Any]:
    """
    Mở khóa tài khoản người dùng.
    """

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == user_id)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng",
        )

    # ========================================================
    # MỞ KHÓA
    # ========================================================

    now = utc_now()

    user.TrangThai = "HoatDong"
    user.KhoaDen = None
    user.SoLanDangNhapSai = 0
    user.LyDoKhoa = None
    user.NgayCapNhat = now

    # Vô hiệu hóa token cũ
    if hasattr(user, "TokenValidAfter"):
        user.TokenValidAfter = now

    _commit_or_raise(db, "Mở khóa tài khoản")

    db.refresh(user)

    return {
        "message": "Mở khóa tài khoản thành công",
        "user": _user_summary(user),
    }



