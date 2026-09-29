from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.nguoi_dung import NguoiDung
from app.schemas.login import LoginRequest
from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()


def login_user(db: Session, request: LoginRequest):
    # Tìm người dùng theo email
    user = (
        db.query(NguoiDung)
        .filter(NguoiDung.Email == request.email)
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

    # Nếu thời gian khóa đã hết thì mở khóa
    if user.KhoaDen and user.KhoaDen <= now:
        user.KhoaDen = None
        user.SoLanDangNhapSai = 0
        user.TrangThai = "HoatDong"
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
        user.SoLanDangNhapSai += 1

        # Sai 5 lần liên tiếp → khóa 15 phút
        if user.SoLanDangNhapSai >= 5:
            user.KhoaDen = now + timedelta(minutes=15)
            user.TrangThai = "BiKhoa"
            user.LyDoKhoa = "Sai mật khẩu 5 lần liên tiếp"

        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Email hoặc mật khẩu không đúng"
        )

    # Đăng nhập đúng → reset số lần sai
    user.SoLanDangNhapSai = 0
    user.KhoaDen = None
    user.TrangThai = "HoatDong"
    user.LyDoKhoa = None
    user.NgayCapNhat = now

    # Lấy vai trò của người dùng
    role_query = text("""
        SELECT vt.VaiTroId, vt.TenVaiTro
        FROM VaiTro vt
        INNER JOIN NguoiDung_VaiTro ndvt
            ON vt.VaiTroId = ndvt.VaiTroId
        WHERE ndvt.NguoiDungId = :nguoi_dung_id
    """)

    roles = db.execute(
        role_query,
        {"nguoi_dung_id": user.NguoiDungId}
    ).mappings().all()

    db.commit()

    return {
        "message": "Đăng nhập thành công",
        "nguoiDungId": user.NguoiDungId,
        "hoTen": user.HoTen,
        "email": user.Email,
        "vaiTro": [
            {
                "vaiTroId": role["VaiTroId"],
                "tenVaiTro": role["TenVaiTro"]
            }
            for role in roles
        ]
    }