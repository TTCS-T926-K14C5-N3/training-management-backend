from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.assignment import (
    Assignment,
    AssignmentGrade,
    AssignmentReopen,
    AssignmentSubmission,
)
from app.models.lich_hoc import LichHoc
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.nguoi_dung import NguoiDung
from app.services.academic_service import (
    ADMIN_ROLE_ID,
    TEACHING_ROLE_IDS,
    TRAINING_MANAGER_ROLE_ID,
    user_role_ids,
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads" / "assignments"


def ensure_upload_size(size: int) -> None:
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Mỗi tệp không được vượt quá {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

def local_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).replace(tzinfo=None)


def to_local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).replace(tzinfo=None)


def can_teach_subject(
    db: Session,
    user: NguoiDung,
    class_id: int,
    subject_id: int,
) -> bool:
    roles = user_role_ids(db, user.NguoiDungId)
    if roles.intersection({ADMIN_ROLE_ID, TRAINING_MANAGER_ROLE_ID}):
        return True
    if not roles.intersection(TEACHING_ROLE_IDS):
        return False
    class_record = db.query(LopHoc).filter(LopHoc.LopHocId == class_id).first()
    return bool(
        class_record
        and (
            class_record.GiangVienId == user.NguoiDungId
            or db.query(LopHocMonHocGiangVien)
            .filter(
                LopHocMonHocGiangVien.LopHocId == class_id,
                LopHocMonHocGiangVien.MonHocId == subject_id,
                LopHocMonHocGiangVien.GiangVienId == user.NguoiDungId,
            )
            .first()
        )
    )


def ensure_assignment_teacher(db: Session, user: NguoiDung, assignment: Assignment) -> None:
    if not can_teach_subject(db, user, assignment.LopHocId, assignment.MonHocId):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công giảng dạy môn học này.",
        )


def ensure_enrolled(db: Session, class_id: int, student_id: int) -> None:
    enrolled = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == class_id,
            LopHocHocVien.HocVienId == student_id,
        )
        .first()
    )
    if enrolled is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn chưa được ghi danh trong lớp của bài tập này.",
        )


def ensure_lesson_matches(db: Session, class_id: int, subject_id: int, lesson_id: int) -> None:
    lesson = db.query(LichHoc).filter(LichHoc.LichHocId == lesson_id).first()
    if lesson is None or lesson.LopHocId != class_id or lesson.MonHocId != subject_id or lesson.TrangThai == "Đã hủy":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Buổi học không thuộc lớp và môn học đã chọn.",
        )


async def save_uploads(files: list[UploadFile]) -> list[dict]:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    stored = []
    try:
        for uploaded in files:
            if not uploaded.filename or not uploaded.filename.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Tệp đính kèm cần có tên hợp lệ.",
                )
            stored_name = f"{uuid4()}.bin"
            path = UPLOAD_ROOT / stored_name
            size = 0
            with path.open("wb") as destination:
                while chunk := await uploaded.read(1024 * 1024):
                    size += len(chunk)
                    ensure_upload_size(size)
                    destination.write(chunk)
            stored.append(
                {
                    "original_name": Path(uploaded.filename.replace("\\", "/")).name[:255],
                    "stored_name": stored_name,
                    "content_type": (uploaded.content_type or "")[:150] or None,
                    "size": size,
                }
            )
    except BaseException:
        delete_stored_files(stored)
        if "path" in locals():
            path.unlink(missing_ok=True)
        raise
    return stored


def delete_stored_files(files: list[dict]) -> None:
    for item in files:
        try:
            (UPLOAD_ROOT / item["stored_name"]).unlink(missing_ok=True)
        except OSError:
            pass


def latest_submission(db: Session, assignment_id: int, student_id: int):
    return (
        db.query(AssignmentSubmission)
        .filter(
            AssignmentSubmission.AssignmentId == assignment_id,
            AssignmentSubmission.HocVienId == student_id,
        )
        .order_by(AssignmentSubmission.VersionNumber.desc())
        .first()
    )


def latest_grade(db: Session, submission_id: int):
    return (
        db.query(AssignmentGrade)
        .filter(AssignmentGrade.SubmissionId == submission_id)
        .order_by(AssignmentGrade.GradedAt.desc(), AssignmentGrade.GradeId.desc())
        .first()
    )


def has_active_reopen(db: Session, assignment_id: int, student_id: int, graded_at: datetime) -> bool:
    reopen = (
        db.query(AssignmentReopen)
        .filter(
            AssignmentReopen.AssignmentId == assignment_id,
            AssignmentReopen.HocVienId == student_id,
            AssignmentReopen.ReopenedAt > graded_at,
        )
        .order_by(AssignmentReopen.ReopenedAt.desc())
        .first()
    )
    return reopen is not None








