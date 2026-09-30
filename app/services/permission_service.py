from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.vai_tro_quyen import VaiTroQuyen
from app.models.quyen import Quyen


def user_has_permission(
    db: Session,
    user: NguoiDung,
    ma_quyen: str
) -> bool:
    """
    Kiểm tra người dùng có quyền hay không.

    Quy tắc:
    - Có quyền -> True
    - Không có quyền -> False
    - Không tìm thấy permission -> False
    """

    permission = (
        db.query(Quyen)
        .filter(
            Quyen.MaQuyen == ma_quyen
        )
        .first()
    )

    # Không tồn tại permission => DENY
    if not permission:
        return False

    permission_exists = (
        db.query(VaiTroQuyen)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.VaiTroId
            == VaiTroQuyen.VaiTroId
        )
        .filter(
            NguoiDungVaiTro.NguoiDungId
            == user.NguoiDungId,
            VaiTroQuyen.QuyenId
            == permission.QuyenId
        )
        .first()
    )

    return permission_exists is not None


def require_permission(
    db: Session,
    user: NguoiDung,
    ma_quyen: str
) -> None:
    """
    Bắt buộc người dùng phải có permission.

    Không có quyền => HTTP 403.
    """

    if not user_has_permission(
        db,
        user,
        ma_quyen
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền thực hiện chức năng này"
        )