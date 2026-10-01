from fastapi import Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import decode_access_token


def require_permission(permission_code: str):
    """
    Kiểm tra người dùng hiện tại có permission hay không.

    Mặc định: DENY nếu không có permission.
    """

    def permission_checker(
        token: str = Depends(lambda: None),
        db: Session = Depends(get_db)
    ):
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Chưa xác thực"
            )

        try:
            payload = decode_access_token(token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token không hợp lệ hoặc đã hết hạn"
            )

        nguoi_dung_id = payload.get("nguoiDungId")

        if not nguoi_dung_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token không chứa thông tin người dùng"
            )

        query = text("""
            SELECT 1
            FROM NguoiDung_VaiTro ndvt
            INNER JOIN VaiTro_Quyen vtq
                ON ndvt.VaiTroId = vtq.VaiTroId
            INNER JOIN Quyen q
                ON vtq.QuyenId = q.QuyenId
            WHERE ndvt.NguoiDungId = :nguoi_dung_id
              AND q.MaQuyen = :permission_code
        """)

        permission_exists = db.execute(
            query,
            {
                "nguoi_dung_id": nguoi_dung_id,
                "permission_code": permission_code
            }
        ).first()

        if not permission_exists:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thực hiện chức năng này"
            )

        return nguoi_dung_id

    return permission_checker