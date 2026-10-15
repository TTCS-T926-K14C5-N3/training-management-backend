from sqlalchemy import Column, ForeignKey, Integer, Unicode
from sqlalchemy.schema import ForeignKeyConstraint

from app.database import Base


class LopHocMonHocGiangVien(Base):
    __tablename__ = "LopHoc_MonHoc_GiangVien"

    LopHocId = Column(Integer, primary_key=True)
    MonHocId = Column(Integer, primary_key=True)
    GiangVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        primary_key=True,
    )
    VaiTro = Column(Unicode(20), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["LopHocId", "MonHocId"],
            ["LopHoc_MonHoc.LopHocId", "LopHoc_MonHoc.MonHocId"],
        ),
    )
