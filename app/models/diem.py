from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Unicode,
    UniqueConstraint,
)

from app.database import Base


class Diem(Base):
    __tablename__ = "Diem"
    __table_args__ = (
        UniqueConstraint(
            "LopHocId",
            "HocVienId",
            "MonHocId",
            "HocKy",
            "NamHoc",
            name="UQ_Diem_HocVien_Lop_Mon_HocKy_NamHoc",
        ),
        CheckConstraint("HocKy BETWEEN 1 AND 3", name="CK_Diem_HocKy"),
        CheckConstraint(
            "DiemQuaTrinh IS NULL OR (DiemQuaTrinh >= 0 AND DiemQuaTrinh <= 10)",
            name="CK_Diem_DiemQuaTrinh",
        ),
        CheckConstraint(
            "DiemGiuaKy IS NULL OR (DiemGiuaKy >= 0 AND DiemGiuaKy <= 10)",
            name="CK_Diem_DiemGiuaKy",
        ),
        CheckConstraint(
            "DiemCuoiKy IS NULL OR (DiemCuoiKy >= 0 AND DiemCuoiKy <= 10)",
            name="CK_Diem_DiemCuoiKy",
        ),
    )

    DiemId = Column(Integer, primary_key=True, autoincrement=True)
    LopHocId = Column(
        Integer,
        ForeignKey("LopHoc.LopHocId"),
        nullable=False,
    )
    HocVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    MonHocId = Column(
        Integer,
        ForeignKey("MonHoc.MonHocId"),
        nullable=False,
    )
    HocKy = Column(Integer, nullable=False)
    NamHoc = Column(Unicode(9), nullable=False)
    DiemQuaTrinh = Column(Numeric(4, 2), nullable=True)
    DiemGiuaKy = Column(Numeric(4, 2), nullable=True)
    DiemCuoiKy = Column(Numeric(4, 2), nullable=True)
    NgayTao = Column(DateTime, nullable=False)
    NgayCapNhat = Column(DateTime, nullable=False)
