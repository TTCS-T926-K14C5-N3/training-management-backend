from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Unicode

from app.database import Base


class StudentEnrollmentAction(Base):
    __tablename__ = "StudentEnrollmentAction"

    ActionId = Column(Integer, primary_key=True, autoincrement=True)
    HocVienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
        index=True,
    )
    LopHocId = Column(
        Integer,
        ForeignKey("LopHoc.LopHocId"),
        nullable=False,
        index=True,
    )
    LopHocDichId = Column(
        Integer,
        ForeignKey("LopHoc.LopHocId"),
        nullable=True,
    )
    LoaiThaoTac = Column(String(30), nullable=False)
    NgayHieuLuc = Column(Date, nullable=False)
    LyDo = Column(Unicode(1000), nullable=False)
    NguoiThucHienId = Column(
        Integer,
        ForeignKey("NguoiDung.NguoiDungId"),
        nullable=False,
    )
    NgayTao = Column(DateTime, nullable=False)