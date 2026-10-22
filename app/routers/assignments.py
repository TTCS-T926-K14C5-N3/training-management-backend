import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.assignment import (
    Assignment,
    AssignmentAttachment,
    AssignmentGrade,
    AssignmentReopen,
    AssignmentSubmission,
    AssignmentSubmissionAttachment,
)
from app.models.lich_hoc import LichHoc
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.services.academic_service import accessible_classes, user_role_ids
from app.services.assignment_service import (
    UPLOAD_ROOT,
    calculate_late_penalty,
    can_teach_subject,
    delete_stored_files,
    ensure_assignment_teacher,
    ensure_enrolled,
    ensure_lesson_matches,
    has_active_reopen,
    latest_grade,
    latest_submission,
    local_now,
    save_uploads,
    to_local_naive,
)
from app.schemas.assignment import (
    AssignmentGradeWrite,
    AssignmentWrite,
    LatePolicyConfigWrite,
    ReopenWrite,
    RepositoryUrl,
)

router = APIRouter(prefix="/assignments", tags=["Assignments"])
ASSIGNMENT_VIEW = "ASSIGNMENT_VIEW"
ASSIGNMENT_CREATE = "ASSIGNMENT_CREATE"
ASSIGNMENT_SUBMIT = "ASSIGNMENT_SUBMIT"
ASSIGNMENT_GRADE = "ASSIGNMENT_GRADE"


def _commit(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from error


def _get_assignment(db: Session, assignment_id: int) -> Assignment:
    assignment = db.query(Assignment).filter(Assignment.AssignmentId == assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài tập.")
    return assignment


def _require_student(user: NguoiDung, db: Session) -> None:
    if 2 not in user_role_ids(db, user.NguoiDungId):
        raise HTTPException(status_code=403, detail="Chức năng này dành cho học viên.")


def _attachment_payload(row: AssignmentAttachment | AssignmentSubmissionAttachment, kind: str) -> dict:
    return {
        "attachmentId": row.AttachmentId,
        "tenTep": row.TenTepGoc,
        "kichThuoc": row.KichThuoc,
        "url": f"/assignments/attachments/{kind}/{row.AttachmentId}",
    }


def _submission_payload(db: Session, submission: AssignmentSubmission | None) -> dict | None:
    if submission is None:
        return None
    grade = latest_grade(db, submission.SubmissionId)
    files = (
        db.query(AssignmentSubmissionAttachment)
        .filter(AssignmentSubmissionAttachment.SubmissionId == submission.SubmissionId)
        .order_by(AssignmentSubmissionAttachment.AttachmentId)
        .all()
    )
    return {
        "submissionId": submission.SubmissionId,
        "version": submission.VersionNumber,
        "repositoryUrl": submission.RepositoryUrl,
        "submittedAt": submission.SubmittedAt.isoformat(),
        "status": "graded" if grade else submission.SubmissionStatus.lower(),
        "late": submission.SubmissionStatus == "Late",
        "grade": float(grade.Diem) if grade else None,
        "rawGrade": float(grade.DiemGoc) if grade and grade.DiemGoc is not None else (float(grade.Diem) if grade else None),
        "penaltyDeduction": float(grade.DiemTruPhat) if grade and grade.DiemTruPhat is not None else 0.0,
        "feedback": grade.NhanXet if grade else None,
        "gradedAt": grade.GradedAt.isoformat() if grade else None,
        "attachments": [_attachment_payload(item, "submission") for item in files],
    }


def _assignment_payload(db: Session, assignment: Assignment, student_id: int | None = None) -> dict:
    class_record = db.query(LopHoc).filter(LopHoc.LopHocId == assignment.LopHocId).first()
    subject = db.query(MonHoc).filter(MonHoc.MonHocId == assignment.MonHocId).first()
    lesson = db.query(LichHoc).filter(LichHoc.LichHocId == assignment.LichHocId).first()
    attachments = (
        db.query(AssignmentAttachment)
        .filter(AssignmentAttachment.AssignmentId == assignment.AssignmentId)
        .order_by(AssignmentAttachment.AttachmentId)
        .all()
    )
    payload = {
        "assignmentId": assignment.AssignmentId,
        "lopHocId": assignment.LopHocId,
        "tenLop": class_record.TenLop if class_record else "",
        "monHocId": assignment.MonHocId,
        "tenMonHoc": subject.TenMonHoc if subject else "",
        "lichHocId": assignment.LichHocId,
        "ngayHoc": lesson.NgayHoc.isoformat() if lesson else None,
        "tieuDe": assignment.TieuDe,
        "moTa": assignment.MoTa,
        "hanNop": assignment.HanNop.isoformat(),
        "diemToiDa": float(assignment.DiemToiDa),
        "choNopMuon": assignment.ChoNopMuon,
        "hanNopMuon": assignment.HanNopMuon.isoformat() if assignment.HanNopMuon else None,
        "loaiPhatNopMuon": assignment.LoaiPhatNopMuon or "none",
        "giaTriPhat": float(assignment.GiaTriPhat) if assignment.GiaTriPhat is not None else 0.0,
        "diemSanToiThieu": float(assignment.DiemSanToiThieu) if assignment.DiemSanToiThieu is not None else 0.0,
        "trangThai": assignment.TrangThai,
        "attachments": [_attachment_payload(item, "assignment") for item in attachments],
    }
    if student_id is not None:
        submission = latest_submission(db, assignment.AssignmentId, student_id)
        payload["submission"] = _submission_payload(db, submission)
        grade = latest_grade(db, submission.SubmissionId) if submission else None
        reopened = bool(
            grade
            and has_active_reopen(
                db,
                assignment.AssignmentId,
                student_id,
                grade.GradedAt,
            )
        )
        can_resubmit = submission is None or grade is None or reopened
        now = local_now()
        if assignment.HanNop < now and not assignment.ChoNopMuon and not reopened:
            can_resubmit = False
        if assignment.HanNopMuon and assignment.HanNopMuon < now and not reopened:
            can_resubmit = False
        payload["canResubmit"] = can_resubmit
    return payload


def _parse_assignment(payload: str) -> AssignmentWrite:
    try:
        return AssignmentWrite.model_validate_json(payload)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors(include_context=False)) from error


def _parse_body(schema, payload: str):
    try:
        return schema.model_validate_json(payload)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors(include_context=False)) from error


@router.get("/options", dependencies=[Depends(require_permission(ASSIGNMENT_VIEW))])
def assignment_options(
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    classes = accessible_classes(db, user)
    options = []
    for class_record in classes:
        subject_rows = (
            db.query(MonHoc)
            .join(LopHocMonHoc, LopHocMonHoc.MonHocId == MonHoc.MonHocId)
            .filter(LopHocMonHoc.LopHocId == class_record.LopHocId)
            .order_by(MonHoc.TenMonHoc)
            .all()
        )
        subjects = []
        for subject in subject_rows:
            if not can_teach_subject(db, user, class_record.LopHocId, subject.MonHocId):
                continue
            lessons = (
                db.query(LichHoc)
                .filter(
                    LichHoc.LopHocId == class_record.LopHocId,
                    LichHoc.MonHocId == subject.MonHocId,
                    LichHoc.TrangThai != "Đã hủy",
                )
                .order_by(LichHoc.NgayHoc.desc(), LichHoc.GioBatDau.desc())
                .all()
            )
            subjects.append({
                "monHocId": subject.MonHocId,
                "tenMonHoc": subject.TenMonHoc,
                "lessons": [{
                    "lichHocId": lesson.LichHocId,
                    "label": f"{lesson.NgayHoc.isoformat()} · {lesson.GioBatDau.strftime('%H:%M')}",
                } for lesson in lessons],
            })
        if subjects:
            options.append({
                "lopHocId": class_record.LopHocId,
                "tenLop": class_record.TenLop,
                "subjects": subjects,
            })
    return options


@router.get("/mine", dependencies=[Depends(require_permission(ASSIGNMENT_VIEW))])
def list_my_assignments(
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    _require_student(user, db)
    class_ids = [row[0] for row in db.query(LopHocHocVien.LopHocId).filter(
        LopHocHocVien.HocVienId == user.NguoiDungId
    ).all()]
    if not class_ids:
        return []
    assignments = (
        db.query(Assignment)
        .filter(Assignment.LopHocId.in_(class_ids), Assignment.TrangThai == "Published")
        .order_by(Assignment.HanNop.asc())
        .all()
    )
    return [_assignment_payload(db, item, user.NguoiDungId) for item in assignments]


@router.get("/teacher", dependencies=[Depends(require_permission(ASSIGNMENT_VIEW))])
def list_teacher_assignments(
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    assignments = db.query(Assignment).order_by(Assignment.NgayTao.desc()).all()
    return [
        _assignment_payload(db, item)
        for item in assignments
        if can_teach_subject(db, user, item.LopHocId, item.MonHocId)
    ]


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission(ASSIGNMENT_CREATE))])
async def create_assignment(
    assignment_json: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()] = [],
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    body = _parse_assignment(assignment_json)
    class_record = db.query(LopHoc).filter(LopHoc.LopHocId == body.lop_hoc_id).first()
    if class_record is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lớp học.")
    if not can_teach_subject(db, user, body.lop_hoc_id, body.mon_hoc_id):
        raise HTTPException(status_code=403, detail="Bạn không được phân công môn học này.")
    due_date = to_local_naive(body.han_nop)
    late_deadline = to_local_naive(body.han_nop_muon) if body.han_nop_muon else None
    if body.cho_nop_muon and late_deadline and late_deadline <= due_date:
        raise HTTPException(status_code=422, detail="Hạn chót nộp muộn phải sau hạn nộp chính thức.")
    if body.diem_san_toi_thieu > body.diem_toi_da:
        raise HTTPException(status_code=422, detail="Điểm sàn tối thiểu không được lớn hơn điểm tối đa.")

    stored = await save_uploads(files)
    now = local_now()
    assignment = Assignment(
        LopHocId=body.lop_hoc_id,
        MonHocId=body.mon_hoc_id,
        LichHocId=body.lich_hoc_id,
        GiangVienId=user.NguoiDungId,
        TieuDe=body.tieu_de,
        MoTa=body.mo_ta,
        HanNop=due_date,
        DiemToiDa=body.diem_toi_da,
        ChoNopMuon=body.cho_nop_muon,
        HanNopMuon=late_deadline if body.cho_nop_muon else None,
        LoaiPhatNopMuon=body.loai_phat_nop_muon if body.cho_nop_muon else "none",
        GiaTriPhat=body.gia_tri_phat if body.cho_nop_muon else Decimal("0.00"),
        DiemSanToiThieu=body.diem_san_toi_thieu if body.cho_nop_muon else Decimal("0.00"),
        TrangThai="Draft",
        NgayTao=now,
        NgayCapNhat=now,
    )
    try:
        db.add(assignment)
        db.flush()
        for item in stored:
            db.add(AssignmentAttachment(
                AssignmentId=assignment.AssignmentId,
                TenTepGoc=item["original_name"],
                TenTepLuu=item["stored_name"],
                LoaiNoiDung=item["content_type"],
                KichThuoc=item["size"],
                NgayTao=now,
            ))
        _commit(db, "Không thể tạo bài tập.")
    except Exception:
        db.rollback()
        delete_stored_files(stored)
        raise
    return _assignment_payload(db, assignment)


@router.post("/{assignment_id}/publish", dependencies=[Depends(require_permission(ASSIGNMENT_CREATE))])
def publish_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    assignment = _get_assignment(db, assignment_id)
    ensure_assignment_teacher(db, user, assignment)
    if assignment.TrangThai != "Draft":
        raise HTTPException(status_code=409, detail="Chỉ có thể phát hành bản nháp.")
    if assignment.HanNop <= local_now():
        raise HTTPException(status_code=422, detail="Hạn nộp phải ở thời điểm tương lai.")
    assignment.TrangThai = "Published"
    assignment.NgayCapNhat = local_now()
    _commit(db, "Không thể phát hành bài tập.")
    return _assignment_payload(db, assignment)


@router.get("/{assignment_id}/roster", dependencies=[Depends(require_permission(ASSIGNMENT_GRADE))])
def assignment_roster(
    assignment_id: int,
    status_filter: str = Query(default="all", alias="status"),
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    assignment = _get_assignment(db, assignment_id)
    ensure_assignment_teacher(db, user, assignment)
    if status_filter not in {"all", "missing", "submitted", "late", "graded"}:
        raise HTTPException(status_code=422, detail="Bộ lọc trạng thái không hợp lệ.")
    enrolled = (
        db.query(NguoiDung)
        .join(LopHocHocVien, LopHocHocVien.HocVienId == NguoiDung.NguoiDungId)
        .filter(LopHocHocVien.LopHocId == assignment.LopHocId)
        .order_by(NguoiDung.HoTen)
        .all()
    )
    roster = []
    counts = {"submitted": 0, "late": 0, "graded": 0, "missing": 0}
    for student in enrolled:
        submission = latest_submission(db, assignment_id, student.NguoiDungId)
        grade = latest_grade(db, submission.SubmissionId) if submission else None
        if submission is None:
            state = "missing"
            counts["missing"] += 1
        else:
            counts["submitted"] += 1
            if submission.SubmissionStatus == "Late":
                counts["late"] += 1
            if grade:
                state = "graded"
                counts["graded"] += 1
            else:
                state = submission.SubmissionStatus.lower()
        item = {
            "studentId": student.NguoiDungId,
            "studentName": student.HoTen,
            "email": student.Email,
            "status": state,
            "submission": _submission_payload(db, submission),
        }
        if (
            status_filter == "all"
            or status_filter == state
            or (status_filter == "submitted" and submission is not None)
            or (
                status_filter == "late"
                and submission is not None
                and submission.SubmissionStatus == "Late"
            )
        ):
            roster.append(item)
    total = len(enrolled)
    return {
        "assignmentId": assignment_id,
        "totalStudents": total,
        "submittedCount": counts["submitted"],
        "gradedCount": counts["graded"],
        "lateCount": counts["late"],
        "missingCount": counts["missing"],
        "progressPercent": round(counts["graded"] * 100 / total, 1) if total else 0,
        "students": roster,
    }


@router.post("/{assignment_id}/submissions", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_permission(ASSIGNMENT_SUBMIT))])
async def submit_assignment(
    assignment_id: int,
    repository_url: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()] = [],
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    _require_student(user, db)
    assignment = _get_assignment(db, assignment_id)
    if assignment.TrangThai != "Published":
        raise HTTPException(status_code=409, detail="Bài tập chưa được phát hành.")
    ensure_enrolled(db, assignment.LopHocId, user.NguoiDungId)
    try:
        repository = RepositoryUrl(url=repository_url).url
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors(include_context=False)) from error
    now = local_now()
    is_late = now > assignment.HanNop
    previous = latest_submission(db, assignment_id, user.NguoiDungId)
    reopened = False
    if previous:
        grade = latest_grade(db, previous.SubmissionId)
        if grade:
            reopened = has_active_reopen(
                db, assignment_id, user.NguoiDungId, grade.GradedAt
            )
            if not reopened:
                raise HTTPException(
                    status_code=409,
                    detail="Bài đã được chấm. Hãy yêu cầu giảng viên mở lại trước khi nộp phiên bản mới.",
                )
    if is_late and assignment.HanNopMuon and now > assignment.HanNopMuon and not reopened:
        raise HTTPException(
            status_code=409,
            detail=f"Đã quá hạn chót nộp muộn ({assignment.HanNopMuon.strftime('%d/%m/%Y %H:%M')}). Bài tập đã đóng nộp bài.",
        )
    if is_late and not assignment.ChoNopMuon and not reopened:
        raise HTTPException(status_code=409, detail="Đã quá hạn và bài tập không nhận bài muộn.")
    stored = await save_uploads(files)
    submission = AssignmentSubmission(
        AssignmentId=assignment_id,
        HocVienId=user.NguoiDungId,
        VersionNumber=(previous.VersionNumber + 1) if previous else 1,
        RepositoryUrl=repository,
        SubmittedAt=now,
        SubmissionStatus="Late" if is_late else "Submitted",
    )
    try:
        db.add(submission)
        db.flush()
        for item in stored:
            db.add(AssignmentSubmissionAttachment(
                SubmissionId=submission.SubmissionId,
                TenTepGoc=item["original_name"],
                TenTepLuu=item["stored_name"],
                LoaiNoiDung=item["content_type"],
                KichThuoc=item["size"],
            ))
        _commit(db, "Không thể lưu phiên bản nộp bài.")
    except Exception:
        db.rollback()
        delete_stored_files(stored)
        raise
    return _submission_payload(db, submission)


@router.post("/submissions/{submission_id}/grade", dependencies=[Depends(require_permission(ASSIGNMENT_GRADE))])
def grade_submission(
    submission_id: int,
    payload_json: Annotated[str, Form()],
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    submission = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.SubmissionId == submission_id
    ).first()
    if submission is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài nộp.")
    assignment = _get_assignment(db, submission.AssignmentId)
    ensure_assignment_teacher(db, user, assignment)
    body = _parse_body(AssignmentGradeWrite, payload_json)
    if body.diem > assignment.DiemToiDa:
        raise HTTPException(status_code=422, detail="Điểm vượt quá số điểm tối đa của bài tập.")

    raw_score = body.diem_goc if body.diem_goc is not None else body.diem
    if raw_score > assignment.DiemToiDa:
        raise HTTPException(status_code=422, detail="Điểm chấm không được vượt quá điểm tối đa.")

    if submission.SubmissionStatus == "Late" and assignment.ChoNopMuon and assignment.LoaiPhatNopMuon != "none":
        deduction, final_score = calculate_late_penalty(
            submitted_at=submission.SubmittedAt,
            due_date=assignment.HanNop,
            max_score=Decimal(str(assignment.DiemToiDa)),
            raw_score=Decimal(str(raw_score)),
            penalty_type=assignment.LoaiPhatNopMuon,
            penalty_value=Decimal(str(assignment.GiaTriPhat or 0)),
            min_score=Decimal(str(assignment.DiemSanToiThieu or 0)),
        )
    else:
        deduction = Decimal("0.00")
        final_score = Decimal(str(raw_score))

    grade = AssignmentGrade(
        SubmissionId=submission.SubmissionId,
        Diem=final_score,
        DiemGoc=raw_score,
        DiemTruPhat=deduction,
        NhanXet=body.nhan_xet,
        GiangVienId=user.NguoiDungId,
        GradedAt=local_now(),
    )
    db.add(grade)
    _commit(db, "Không thể lưu điểm.")
    return _submission_payload(db, submission)


@router.post("/{assignment_id}/students/{student_id}/reopen", dependencies=[Depends(require_permission(ASSIGNMENT_GRADE))])
def reopen_submission(
    assignment_id: int,
    student_id: int,
    body: ReopenWrite,
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    assignment = _get_assignment(db, assignment_id)
    ensure_assignment_teacher(db, user, assignment)
    ensure_enrolled(db, assignment.LopHocId, student_id)
    submission = latest_submission(db, assignment_id, student_id)
    if submission is None:
        raise HTTPException(status_code=409, detail="Học viên chưa nộp bài.")
    grade = latest_grade(db, submission.SubmissionId)
    if grade is None:
        raise HTTPException(status_code=409, detail="Chỉ có thể mở lại bài đã chấm.")
    if not body.ly_do:
        raise HTTPException(status_code=422, detail="Vui lòng nhập lý do mở lại bài.")
    db.add(AssignmentReopen(
        AssignmentId=assignment_id,
        HocVienId=student_id,
        GiangVienId=user.NguoiDungId,
        ReopenedAt=local_now(),
        LyDo=body.ly_do,
    ))
    _commit(db, "Không thể mở lại bài nộp.")
    return {"message": "Đã mở lại bài để học viên nộp phiên bản mới."}


@router.get("/attachments/{kind}/{attachment_id}", dependencies=[Depends(require_permission(ASSIGNMENT_VIEW))])
def download_attachment(
    kind: str,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    if kind == "assignment":
        attachment = db.query(AssignmentAttachment).filter(
            AssignmentAttachment.AttachmentId == attachment_id
        ).first()
        if attachment is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy tệp.")
        assignment = _get_assignment(db, attachment.AssignmentId)
        if assignment.TrangThai != "Published" and assignment.GiangVienId != user.NguoiDungId:
            raise HTTPException(status_code=403, detail="Không được phép tải tệp này.")
        roles = user_role_ids(db, user.NguoiDungId)
        if assignment.GiangVienId != user.NguoiDungId and not can_teach_subject(
            db, user, assignment.LopHocId, assignment.MonHocId
        ):
            if 2 not in roles:
                raise HTTPException(status_code=403, detail="Không được phép tải tệp này.")
            ensure_enrolled(db, assignment.LopHocId, user.NguoiDungId)
        stored_name = attachment.TenTepLuu
        original_name = attachment.TenTepGoc
    elif kind == "submission":
        attachment = db.query(AssignmentSubmissionAttachment).filter(
            AssignmentSubmissionAttachment.AttachmentId == attachment_id
        ).first()
        if attachment is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy tệp.")
        submission = db.query(AssignmentSubmission).filter(
            AssignmentSubmission.SubmissionId == attachment.SubmissionId
        ).first()
        assignment = _get_assignment(db, submission.AssignmentId)
        if submission.HocVienId != user.NguoiDungId:
            ensure_assignment_teacher(db, user, assignment)
        stored_name = attachment.TenTepLuu
        original_name = attachment.TenTepGoc
    else:
        raise HTTPException(status_code=404, detail="Không tìm thấy loại tệp.")
    path = UPLOAD_ROOT / Path(stored_name).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Tệp không còn tồn tại trên máy chủ.")
    return FileResponse(path, filename=original_name)


def _late_policy_payload(assignment: Assignment) -> dict:
    parts = []
    if assignment.ChoNopMuon:
        if assignment.HanNopMuon:
            parts.append(f"Hạn chót: {assignment.HanNopMuon.strftime('%d/%m/%Y %H:%M')}")
        p_type = assignment.LoaiPhatNopMuon or "none"
        p_val = float(assignment.GiaTriPhat) if assignment.GiaTriPhat is not None else 0.0
        min_floor = float(assignment.DiemSanToiThieu) if assignment.DiemSanToiThieu is not None else 0.0
        if p_type == "none":
            parts.append("Không trừ điểm phạt")
        elif p_type == "percentage_per_day":
            parts.append(f"Trừ {p_val}%/ngày")
        elif p_type == "fixed_percentage":
            parts.append(f"Trừ {p_val}% cố định")
        elif p_type == "fixed_points":
            parts.append(f"Trừ {p_val}đ")
        if p_type != "none" and min_floor > 0:
            parts.append(f"Điểm sàn: {min_floor}đ")
        desc = f"Cho phép nộp muộn ({' · '.join(parts)})" if parts else "Cho phép nộp muộn"
    else:
        desc = "Không nhận bài muộn"

    return {
        "assignmentId": assignment.AssignmentId,
        "tieuDe": assignment.TieuDe,
        "hanNop": assignment.HanNop.isoformat(),
        "diemToiDa": float(assignment.DiemToiDa),
        "choNopMuon": assignment.ChoNopMuon,
        "hanNopMuon": assignment.HanNopMuon.isoformat() if assignment.HanNopMuon else None,
        "loaiPhatNopMuon": assignment.LoaiPhatNopMuon or "none",
        "giaTriPhat": float(assignment.GiaTriPhat) if assignment.GiaTriPhat is not None else 0.0,
        "diemSanToiThieu": float(assignment.DiemSanToiThieu) if assignment.DiemSanToiThieu is not None else 0.0,
        "moTaChinhSach": desc,
    }


@router.get("/{assignment_id}/late-policy", dependencies=[Depends(require_permission(ASSIGNMENT_VIEW))])
def get_late_policy(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    assignment = _get_assignment(db, assignment_id)
    roles = user_role_ids(db, user.NguoiDungId)
    if not (can_teach_subject(db, user, assignment.LopHocId, assignment.MonHocId) or 2 in roles):
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem chính sách nộp muộn của bài tập này.")
    if 2 in roles and not can_teach_subject(db, user, assignment.LopHocId, assignment.MonHocId):
        ensure_enrolled(db, assignment.LopHocId, user.NguoiDungId)
    return _late_policy_payload(assignment)


@router.put("/{assignment_id}/late-policy", dependencies=[Depends(require_permission(ASSIGNMENT_CREATE))])
def update_late_policy(
    assignment_id: int,
    body: LatePolicyConfigWrite,
    db: Session = Depends(get_db),
    user: NguoiDung = Depends(get_current_user),
):
    assignment = _get_assignment(db, assignment_id)
    ensure_assignment_teacher(db, user, assignment)

    if body.cho_nop_muon:
        late_deadline = to_local_naive(body.han_nop_muon) if body.han_nop_muon else None
        if late_deadline and late_deadline <= assignment.HanNop:
            raise HTTPException(status_code=422, detail="Hạn chót nộp muộn phải sau hạn nộp chính thức.")
        if body.diem_san_toi_thieu > assignment.DiemToiDa:
            raise HTTPException(status_code=422, detail="Điểm sàn tối thiểu không được lớn hơn điểm tối đa.")

        assignment.ChoNopMuon = True
        assignment.HanNopMuon = late_deadline
        assignment.LoaiPhatNopMuon = body.loai_phat_nop_muon
        assignment.GiaTriPhat = body.gia_tri_phat
        assignment.DiemSanToiThieu = body.diem_san_toi_thieu
    else:
        assignment.ChoNopMuon = False
        assignment.HanNopMuon = None
        assignment.LoaiPhatNopMuon = "none"
        assignment.GiaTriPhat = Decimal("0.00")
        assignment.DiemSanToiThieu = Decimal("0.00")

    assignment.NgayCapNhat = local_now()
    _commit(db, "Không thể cập nhật cấu hình chính sách nộp muộn.")
    result = _late_policy_payload(assignment)
    result["message"] = "Đã cập nhật cấu hình chính sách nộp muộn thành công."
    return result










