from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Unicode,
    UnicodeText,
    UniqueConstraint,
)

from app.database import Base


class LichHocThongBao(Base):
    __tablename__ = "LichHoc_ThongBao"
    __table_args__ = (
        UniqueConstraint(
            "SuKienId",
            "NguoiNhanId",
            name="UQ_LichHoc_ThongBao_SuKien_NguoiNhan",
        ),
        Index(
            "IX_LichHoc_ThongBao_TrangThai",
            "TrangThai",
            "LichHocThongBaoId",
        ),
    )

    LichHocThongBaoId = Column(Integer, primary_key=True, autoincrement=True)
    SuKienId = Column(Unicode(36), nullable=False)
    LichHocId = Column(
        Integer,
        ForeignKey("LichHoc.LichHocId"),
        nullable=False,
    )
    NguoiNhanId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    LoaiSuKien = Column(Unicode(30), nullable=False)
    NoiDung = Column(UnicodeText, nullable=False)
    DuLieuCu = Column(UnicodeText, nullable=False)
    DuLieuMoi = Column(UnicodeText, nullable=False)
    LyDo = Column(Unicode(1000), nullable=True)
    NguoiThucHienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    ThoiDiemPhatSinh = Column(DateTime, nullable=False)
    TrangThai = Column(Unicode(20), nullable=False, default="Chờ gửi")
    SoLanGui = Column(Integer, nullable=False, default=0)
    ThoiDiemGuiCuoi = Column(DateTime, nullable=True)
    ThoiDiemGui = Column(DateTime, nullable=True)
    LoiGui = Column(Unicode(2000), nullable=True)
