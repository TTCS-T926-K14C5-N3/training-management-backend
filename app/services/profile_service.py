from datetime import datetime

from sqlalchemy.orm import Session

from app.models.nguoi_dung import NguoiDung
from app.schemas.update_profile import UpdateProfileRequest


def get_my_profile(
    db: Session,
    current_user: NguoiDung,
) -> NguoiDung:
    """
    Lấy thông tin hồ sơ của người dùng đang đăng nhập.
    """

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId == current_user.NguoiDungId
        )
        .first()
    )

    if not user:
        raise ValueError("Không tìm thấy người dùng")

    return user


def update_my_profile(
    db: Session,
    current_user: NguoiDung,
    data: UpdateProfileRequest,
) -> NguoiDung:
    """
    Cập nhật hồ sơ cá nhân.

    Người dùng chỉ được sửa:
    - Họ tên
    - Số điện thoại
    - Ngày sinh
    - Địa chỉ

    Không được sửa:
    - Email
    - Vai trò
    - Mật khẩu
    - Trạng thái tài khoản
    """

    user = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId == current_user.NguoiDungId
        )
        .first()
    )

    if not user:
        raise ValueError("Không tìm thấy người dùng")

    user.HoTen = data.ho_ten
    user.SoDienThoai = data.so_dien_thoai
    user.NgaySinh = data.ngay_sinh
    user.DiaChi = data.dia_chi
    user.NgayCapNhat = datetime.now()

    db.commit()
    db.refresh(user)

    return user