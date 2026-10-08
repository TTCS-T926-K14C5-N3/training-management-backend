import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException
from pwdlib import PasswordHash
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import create_access_token, decode_access_token
from app.models.nguoi_dung import NguoiDung
from app.models.revoked_token import RevokedToken
from app.models.token_mat_khau import TokenMatKhau
from app.models.token_kich_hoat import TokenKichHoat
from app.schemas.forgot_password import ForgotPasswordRequest
from app.schemas.login import LoginRequest
from app.schemas.nguoi_dung import NguoiDungCreate, NguoiDungLock
from app.schemas.register import RegisterRequest
from app.schemas.reset_password import ResetPasswordRequest
from app.services.email_service import send_reset_password_email


password_hash = PasswordHash.recommended()


def _user_data(user: NguoiDung) -> dict:
    return {
        "nguoiDungId": user.NguoiDungId,
        "hoTen": user.HoTen,
        "email": user.Email,
        "trangThai": user.TrangThai,
    }


def _find_user(db: Session, user_id: int) -> NguoiDung:
    user = db.query(NguoiDung).filter(NguoiDung.NguoiDungId == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    return user


def register_user(db: Session, request: RegisterRequest):
    email = str(request.email).strip().lower()
    existing_user = db.query(NguoiDung).filter(NguoiDung.Email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email đã được sử dụng")

    user = NguoiDung(
        HoTen=request.ho_ten.strip(),
        Email=email,
        SoDienThoai=request.so_dien_thoai.strip() if request.so_dien_thoai else None,
        MatKhauHash=password_hash.hash(request.password),
        TrangThai="HoatDong",
        SoLanDangNhapSai=0,
        KhoaDen=None,
        LyDoKhoa=None,
        NgayTao=datetime.now(),
        NgayCapNhat=datetime.now(),
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Không thể tạo tài khoản")

    return {"message": "Đăng ký thành công", "user": _user_data(user)}


def create_user(db: Session, request: NguoiDungCreate):
    email = str(request.email).strip().lower()
    exists = db.query(NguoiDung).filter(NguoiDung.Email == email).first()
    if exists:
        raise HTTPException(status_code=400, detail="Email đã được sử dụng")

    user = NguoiDung(
        HoTen=request.ho_ten.strip(),
        Email=email,
        SoDienThoai=request.so_dien_thoai,
        MatKhauHash=password_hash.hash(request.password),
        TrangThai="HoatDong",
        SoLanDangNhapSai=0,
        KhoaDen=None,
        LyDoKhoa=None,
        TokenValidAfter=None,
        NgayTao=datetime.now(),
        NgayCapNhat=datetime.now(),
    )

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Không thể tạo người dùng")

    return {"message": "Tạo người dùng thành công", "user": _user_data(user)}


def login_user(db: Session, request: LoginRequest):
    email = str(request.email).strip().lower()
    user = db.query(NguoiDung).filter(NguoiDung.Email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")

    now = datetime.now()
    if user.KhoaDen and user.KhoaDen > now:
        reason = f": {user.LyDoKhoa}" if user.LyDoKhoa else ""
        if user.TrangThai == "BiKhoa":
            raise HTTPException(status_code=423, detail=f"Tài khoản đã bị khóa{reason}")
        raise HTTPException(status_code=423, detail="Tài khoản đang bị khóa tạm thời")

    if user.KhoaDen and user.KhoaDen <= now:
        user.KhoaDen = None
        user.SoLanDangNhapSai = 0
        user.TrangThai = "HoatDong"
        user.LyDoKhoa = None

    if user.TrangThai == "BiKhoa":
        reason = f": {user.LyDoKhoa}" if user.LyDoKhoa else ""
        raise HTTPException(status_code=423, detail=f"Tài khoản đã bị khóa{reason}")

    try:
        password_correct = password_hash.verify(request.password, user.MatKhauHash)
    except Exception:
        password_correct = False

    if not password_correct:
        user.SoLanDangNhapSai = (user.SoLanDangNhapSai or 0) + 1

        if user.SoLanDangNhapSai >= 5:
            user.KhoaDen = now + timedelta(minutes=15)
            user.TrangThai = "BiKhoa"
            user.LyDoKhoa = "Sai mật khẩu 5 lần liên tiếp"
            db.commit()

            raise HTTPException(
                status_code=423,
                detail="Tài khoản đã bị khóa tạm thời 15 phút do nhập sai mật khẩu 5 lần liên tiếp",
            )

        db.commit()
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")

    user.SoLanDangNhapSai = 0
    user.KhoaDen = None
    user.LyDoKhoa = None
    user.TrangThai = "HoatDong"
    user.NgayCapNhat = now
    db.commit()
    db.refresh(user)

    user_id = user.NguoiDungId
    roles = db.execute(
        text("""
            SELECT vt.VaiTroId, vt.TenVaiTro
            FROM NguoiDung_VaiTro ndvt
            INNER JOIN VaiTro vt ON ndvt.VaiTroId = vt.VaiTroId
            WHERE ndvt.NguoiDungId = :nguoi_dung_id
            ORDER BY vt.VaiTroId
        """),
        {"nguoi_dung_id": user_id},
    ).mappings().all()

    permissions = db.execute(
        text("""
            SELECT DISTINCT q.QuyenId, q.MaQuyen, q.TenQuyen
            FROM NguoiDung_VaiTro ndvt
            INNER JOIN VaiTroQuyen vtq ON ndvt.VaiTroId = vtq.VaiTroId
            INNER JOIN Quyen q ON vtq.QuyenId = q.QuyenId
            WHERE ndvt.NguoiDungId = :nguoi_dung_id
            ORDER BY q.QuyenId
        """),
        {"nguoi_dung_id": user_id},
    ).mappings().all()

    return {
        "message": "Đăng nhập thành công",
        "access_token": create_access_token({
            "sub": user.Email,
            "user_id": user_id,
            "roles": [role["TenVaiTro"] for role in roles],
        }),
        "token_type": "bearer",
        "nguoiDungId": user.NguoiDungId,
        "hoTen": user.HoTen,
        "email": user.Email,
        "vaiTro": [
            {"vaiTroId": role["VaiTroId"], "tenVaiTro": role["TenVaiTro"]}
            for role in roles
        ],
        "quyen": [
            {
                "quyenId": permission["QuyenId"],
                "maQuyen": permission["MaQuyen"],
                "tenQuyen": permission["TenQuyen"],
            }
            for permission in permissions
        ],
    }


def logout_user(db: Session, token: str):
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        # Chuẩn hóa theo task: "Token hết hạn"
        raise HTTPException(status_code=401, detail="Token hết hạn")
    except jwt.InvalidTokenError:
        # Chuẩn hóa theo task: "Token không hợp lệ"
        raise HTTPException(status_code=401, detail="Token không hợp lệ")

    jti, exp = payload.get("jti"), payload.get("exp")
    if not jti or not exp:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")

    exists = db.query(RevokedToken).filter(RevokedToken.Jti == jti).first()
    if exists:
        return {"message": "Đăng xuất thành công"}

    revoked = RevokedToken(
        Jti=jti,
        ExpiresAt=datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None),
    )
    try:
        db.add(revoked)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Không thể đăng xuất")

    return {"message": "Đăng xuất thành công"}


def update_password(
    db: Session,
    user: NguoiDung,
    current_password: str,
    new_password: str,
):
    try:
        correct = password_hash.verify(current_password, user.MatKhauHash)
    except Exception:
        correct = False
    if not correct:
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")

    now = datetime.now()
    user.MatKhauHash = password_hash.hash(new_password)
    user.NgayCapNhat = now
    user.TokenValidAfter = now

    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Không thể cập nhật mật khẩu")

    return {"message": "Cập nhật mật khẩu thành công"}


def forgot_password(db: Session, request: ForgotPasswordRequest):
    email = str(request.email).strip().lower()
    message = (
        "Nếu email tồn tại trong hệ thống, "
        "hướng dẫn đặt lại mật khẩu đã được gửi."
    )
    user = db.query(NguoiDung).filter(NguoiDung.Email == email).first()
    if not user:
        return {"message": message}

    raw_token = secrets.token_urlsafe(32)
    now = datetime.now()
    reset_token = TokenMatKhau(
        NguoiDungId=user.NguoiDungId,
        Token=hashlib.sha256(raw_token.encode()).hexdigest(),
        ThoiGianTao=now,
        ThoiGianHetHan=now + timedelta(minutes=30),
        DaSuDung=False,
    )
    try:
        db.add(reset_token)
        db.commit()
    except Exception:
        db.rollback()
        return {"message": message}

    reset_link = f"http://localhost:5173/reset-password?token={raw_token}"
    try:
        send_reset_password_email(recipient_email=user.Email, reset_link=reset_link)
    except Exception:
        pass
    return {"message": message}

def activate_account(db: Session, token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    activation_token = (
        db.query(TokenKichHoat)
        .filter(
            TokenKichHoat.Token == token_hash,
            TokenKichHoat.DaSuDung == False,
        )
        .first()
    )

    if not activation_token:
        raise HTTPException(
            status_code=400,
            detail="Token kích hoạt không hợp lệ",
        )

    now = datetime.now()

    if activation_token.ThoiGianHetHan < now:
        activation_token.DaSuDung = True
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Token kích hoạt đã hết hạn",
        )

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId == activation_token.NguoiDungId
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy người dùng",
        )

    user.NgayCapNhat = now

    activation_token.DaSuDung = True

    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Không thể kích hoạt tài khoản",
        )

    return {
        "message": "Kích hoạt tài khoản thành công",
        "nguoiDungId": user.NguoiDungId,
        "email": user.Email,
    }

def validate_reset_token(db: Session, token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    reset_token = (
        db.query(TokenMatKhau)
        .filter(
            TokenMatKhau.Token == token_hash,
            TokenMatKhau.DaSuDung == False,
        )
        .first()
    )

    if not reset_token:
        raise HTTPException(
            status_code=400,
            detail="Token không hợp lệ",
        )

    now = datetime.now()

    if reset_token.ThoiGianHetHan < now:
        reset_token.DaSuDung = True
        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Token đã hết hạn",
        )

    return {
        "message": "Token hợp lệ",
    }

def reset_password(db: Session, request: ResetPasswordRequest):
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    reset_token = (
        db.query(TokenMatKhau)
        .filter(
            TokenMatKhau.Token == token_hash,
            TokenMatKhau.DaSuDung == False,
        )
        .first()
    )
    if not reset_token:
        raise HTTPException(status_code=400, detail="Token không hợp lệ")

    now = datetime.now()
    if reset_token.ThoiGianHetHan < now:
        reset_token.DaSuDung = True
        db.commit()
        raise HTTPException(status_code=400, detail="Token đã hết hạn")

    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == reset_token.NguoiDungId)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    user.MatKhauHash = password_hash.hash(request.new_password)
    user.TokenValidAfter = now
    user.NgayCapNhat = now
    reset_token.DaSuDung = True

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Không thể đặt lại mật khẩu")

    return {"message": "Đặt lại mật khẩu thành công"}


def update_user(db: Session, user_id: int, request):
    user = _find_user(db, user_id)

    if request.email:
        email = str(request.email).strip().lower()
        exists = (
            db.query(NguoiDung)
            .filter(
                NguoiDung.Email == email,
                NguoiDung.NguoiDungId != user_id,
            )
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="Email đã tồn tại")
        user.Email = email

    if request.ho_ten:
        user.HoTen = request.ho_ten.strip()
    if request.so_dien_thoai:
        user.SoDienThoai = request.so_dien_thoai.strip()
    user.NgayCapNhat = datetime.now()

    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Không thể cập nhật")

    return {"message": "Cập nhật thành công"}


def lock_user(db: Session, user_id: int, request: NguoiDungLock):
    user = _find_user(db, user_id)
    user.TrangThai = "BiKhoa"
    user.KhoaDen = None
    user.LyDoKhoa = (
        request.ly_do_khoa.strip()
        if request.ly_do_khoa
        else "Bị khóa bởi quản trị viên"
    )
    user.TokenValidAfter = datetime.now()
    user.NgayCapNhat = datetime.now()

    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Không thể khóa tài khoản")

    return {
        "message": "Khóa tài khoản thành công",
        "nguoiDungId": user.NguoiDungId,
        "trangThai": user.TrangThai,
        "lyDoKhoa": user.LyDoKhoa,
    }


def unlock_user(db: Session, user_id: int):
    user = _find_user(db, user_id)
    if user.TrangThai != "BiKhoa":
        raise HTTPException(status_code=400, detail="Tài khoản chưa bị khóa")

    user.TrangThai = "HoatDong"
    user.KhoaDen = None
    user.LyDoKhoa = None
    user.SoLanDangNhapSai = 0
    user.TokenValidAfter = datetime.now()
    user.NgayCapNhat = datetime.now()

    try:
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Không thể mở khóa tài khoản")

    return {
        "message": "Mở khóa tài khoản thành công",
        "user": {
            **_user_data(user),
            "ngayCapNhat": user.NgayCapNhat,
        },
    }
