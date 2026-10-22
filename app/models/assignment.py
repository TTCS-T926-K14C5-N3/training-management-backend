from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Unicode,
    UnicodeText,
)

from app.database import Base


class Assignment(Base):
    __tablename__ = "Assignment"
    __table_args__ = (
        ForeignKeyConstraint(
            ["LopHocId", "MonHocId"],
            ["LopHoc_MonHoc.LopHocId", "LopHoc_MonHoc.MonHocId"],
            name="FK_Assignment_ClassSubject",
        ),
        CheckConstraint("DiemToiDa > 0", name="CK_Assignment_Points"),
        CheckConstraint(
            "TrangThai IN ('Draft', 'Published')",
            name="CK_Assignment_Status",
        ),
    )

    AssignmentId = Column(Integer, primary_key=True, autoincrement=True)
    LopHocId = Column(Integer, nullable=False)
    MonHocId = Column(Integer, nullable=False)
    LichHocId = Column(Integer, ForeignKey("LichHoc.LichHocId"), nullable=False)
    GiangVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    TieuDe = Column(Unicode(200), nullable=False)
    MoTa = Column(UnicodeText, nullable=False)
    HanNop = Column(DateTime, nullable=False)
    DiemToiDa = Column(Numeric(7, 2), nullable=False)
    ChoNopMuon = Column(Boolean, nullable=False, default=False)
    HanNopMuon = Column(DateTime, nullable=True)
    LoaiPhatNopMuon = Column(String(30), nullable=False, default="none")
    GiaTriPhat = Column(Numeric(7, 2), nullable=False, default=0)
    DiemSanToiThieu = Column(Numeric(7, 2), nullable=False, default=0)
    TrangThai = Column(String(20), nullable=False, default="Draft")
    NgayTao = Column(DateTime, nullable=False)
    NgayCapNhat = Column(DateTime, nullable=False)


class AssignmentAttachment(Base):
    __tablename__ = "AssignmentAttachment"

    AttachmentId = Column(Integer, primary_key=True, autoincrement=True)
    AssignmentId = Column(
        Integer, ForeignKey("Assignment.AssignmentId"), nullable=False
    )
    TenTepGoc = Column(Unicode(255), nullable=False)
    TenTepLuu = Column(String(36), nullable=False, unique=True)
    LoaiNoiDung = Column(String(150), nullable=True)
    KichThuoc = Column(Integer, nullable=False)
    NgayTao = Column(DateTime, nullable=False)


class AssignmentSubmission(Base):
    __tablename__ = "AssignmentSubmission"
    __table_args__ = (
        CheckConstraint("VersionNumber > 0", name="CK_AssignmentSubmission_Version"),
        CheckConstraint(
            "SubmissionStatus IN ('Submitted', 'Late')",
            name="CK_AssignmentSubmission_Status",
        ),
    )

    SubmissionId = Column(Integer, primary_key=True, autoincrement=True)
    AssignmentId = Column(
        Integer, ForeignKey("Assignment.AssignmentId"), nullable=False
    )
    HocVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    VersionNumber = Column(Integer, nullable=False)
    RepositoryUrl = Column(Unicode(1000), nullable=False)
    SubmittedAt = Column(DateTime, nullable=False)
    SubmissionStatus = Column(String(20), nullable=False)


class AssignmentSubmissionAttachment(Base):
    __tablename__ = "AssignmentSubmissionAttachment"

    AttachmentId = Column(Integer, primary_key=True, autoincrement=True)
    SubmissionId = Column(
        Integer, ForeignKey("AssignmentSubmission.SubmissionId"), nullable=False
    )
    TenTepGoc = Column(Unicode(255), nullable=False)
    TenTepLuu = Column(String(36), nullable=False, unique=True)
    LoaiNoiDung = Column(String(150), nullable=True)
    KichThuoc = Column(Integer, nullable=False)


class AssignmentGrade(Base):
    __tablename__ = "AssignmentGrade"

    GradeId = Column(Integer, primary_key=True, autoincrement=True)
    SubmissionId = Column(
        Integer, ForeignKey("AssignmentSubmission.SubmissionId"), nullable=False
    )
    Diem = Column(Numeric(7, 2), nullable=False)
    DiemGoc = Column(Numeric(7, 2), nullable=True)
    DiemTruPhat = Column(Numeric(7, 2), nullable=False, default=0)
    NhanXet = Column(Unicode(2000), nullable=True)
    GiangVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    GradedAt = Column(DateTime, nullable=False)


class AssignmentReopen(Base):
    __tablename__ = "AssignmentReopen"

    ReopenId = Column(Integer, primary_key=True, autoincrement=True)
    AssignmentId = Column(
        Integer, ForeignKey("Assignment.AssignmentId"), nullable=False
    )
    HocVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    GiangVienId = Column(Integer, ForeignKey("NguoiDung.NguoiDungId"), nullable=False)
    ReopenedAt = Column(DateTime, nullable=False)
    LyDo = Column(Unicode(1000), nullable=False)
