from sqlalchemy import Column, ForeignKey, Integer

from app.database import Base


class LopHocMonHoc(Base):
    __tablename__ = "LopHoc_MonHoc"

    LopHocId = Column(
        Integer,
        ForeignKey("LopHoc.LopHocId"),
        primary_key=True,
    )
    MonHocId = Column(
        Integer,
        ForeignKey("MonHoc.MonHocId"),
        primary_key=True,
    )
