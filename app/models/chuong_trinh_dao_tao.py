from sqlalchemy import CheckConstraint, Column, DateTime, Integer, Numeric, Unicode

from app.database import Base


class ChuongTrinhDaoTao(Base):
    __tablename__ = "ChuongTrinhDaoTao"
    __table_args__ = (
        CheckConstraint(
            "TongThoiLuong > 0",
            name="CK_ChuongTrinhDaoTao_TongThoiLuong",
        ),
        CheckConstraint(
            "HocPhiChuan >= 0",
            name="CK_ChuongTrinhDaoTao_HocPhiChuan",
        ),
    )

    ChuongTrinhId = Column(Integer, primary_key=True, autoincrement=True)
    MaChuongTrinh = Column(Unicode(30), nullable=False, unique=True)
    TenChuongTrinh = Column(Unicode(150), nullable=False)
    MoTa = Column(Unicode(1000), nullable=True)
    TongThoiLuong = Column(Integer, nullable=False)
    HocPhiChuan = Column(Numeric(12, 2), nullable=False)
    TrangThai = Column(
        Unicode(30),
        nullable=False,
        default="Đang áp dụng",
    )
    NgayTao = Column(DateTime, nullable=False)
    NgayCapNhat = Column(DateTime, nullable=True)
