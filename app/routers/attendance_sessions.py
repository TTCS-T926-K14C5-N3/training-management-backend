import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.absence_request import (
    AbsenceRequest as SessionAbsenceRequest,
    AttendanceAudit as SessionAttendanceAudit,
    AttendanceNotification as SessionAttendanceNotification,
)
from app.models.diem_danh_buoi_hoc import DiemDanhBuoiHoc
from app.models.lich_hoc import LichHoc
from app.models.lop_hoc import LopHoc
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.schemas.attendance import AbsenceRequestDecision, AbsenceRequestWrite
from app.services.academic_service import (
    STUDENT_ROLE_ID,
    TEACHING_ROLE_IDS,
    has_schedule_wide_scope,
    user_role_ids,
)
from app.services.business_time import business_now_naive
from app.services.email_service import send_absence_request_approved_email

from .schedules import (
    CANCELLED,
    _attendance_roster,
    _acquire_schedule_write_lock,
    _get_schedule_or_404,
    _ensure_attendance_scope,
)


router = APIRouter(prefix="/attendance/sessions", tags=["Session attendance"])
audit_router = APIRouter(prefix="/attendance", tags=["Session attendance"])
logger = logging.getLogger(__name__)
EVIDENCE_DIRECTORY = (
    Path(__file__).resolve().parents[2] / "app" / "uploads" / "absence-evidence"
)
MAX_EVIDENCE_SIZE = 5 * 1024 * 1024
EVIDENCE_TYPES = {
    ".pdf": ("application/pdf", lambda data: data.startswith(b"%PDF-")),
    ".png": ("image/png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda data: data.startswith(b"\xff\xd8\xff")),
}


def _get_absence_request_or_404(db: Session, request_id: int) -> SessionAbsenceRequest:
    request = (
        db.query(SessionAbsenceRequest)
        .filter(SessionAbsenceRequest.RequestId == request_id)
        .first()
    )
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy đơn xin phép vắng.",
        )
    return request


def _student_only(db: Session, user: NguoiDung) -> None:
    if STUDENT_ROLE_ID not in user_role_ids(db, user.NguoiDungId):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ học viên mới được gửi đơn xin phép vắng.",
        )


def _ensure_absence_review_scope(
    db: Session,
    schedule: LichHoc,
    current_user: NguoiDung,
) -> None:
    role_ids = user_role_ids(db, current_user.NguoiDungId)
    if has_schedule_wide_scope(db, current_user.NguoiDungId, role_ids):
        return
    if (
        role_ids.intersection(TEACHING_ROLE_IDS)
        and schedule.GiangVienId == current_user.NguoiDungId
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Chỉ giảng viên được phân công buổi học mới được xử lý đơn.",
    )


def _request_payload(db: Session, item: SessionAbsenceRequest) -> dict:
    schedule = _get_schedule_or_404(db, item.LichHocId)
    class_record = (
        db.query(LopHoc).filter(LopHoc.LopHocId == schedule.LopHocId).first()
    )
    student = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == item.HocVienId)
        .first()
    )
    teacher = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == schedule.GiangVienId)
        .first()
    )
    subject = (
        db.query(MonHoc)
        .filter(MonHoc.MonHocId == schedule.MonHocId)
        .first()
    )
    return {
        "requestId": item.RequestId,
        "scheduleId": schedule.LichHocId,
        "classId": schedule.LopHocId,
        "classCode": class_record.MaLop if class_record else None,
        "className": class_record.TenLop if class_record else None,
        "studentId": item.HocVienId,
        "studentName": student.HoTen if student else None,
        "date": schedule.NgayHoc.isoformat(),
        "startTime": schedule.GioBatDau.strftime("%H:%M"),
        "endTime": schedule.GioKetThuc.strftime("%H:%M"),
        "subjectName": subject.TenMonHoc if subject else None,
        "teacherName": teacher.HoTen if teacher else None,
        "reason": item.LyDo,
        "evidence": (
            f"/attendance/sessions/absence-requests/{item.RequestId}/evidence"
            if item.TepMinhChungPath
            else None
        ),
        "evidenceName": item.TepMinhChungTen,
        "status": {
            "Chờ duyệt": "pending",
            "Đã duyệt": "approved",
            "Từ chối": "rejected",
        }.get(item.TrangThai, item.TrangThai),
        "reviewReason": item.LyDoDuyet,
        "createdAt": item.NgayTao.isoformat(),
        "reviewedAt": item.ThoiDiemDuyet.isoformat() if item.ThoiDiemDuyet else None,
    }


def _create_absence_request(
    db: Session,
    request_data: AbsenceRequestWrite,
    current_user: NguoiDung,
    *,
    evidence: tuple[bytes, str, str] | None = None,
) -> dict:
    _student_only(db, current_user)
    schedule = _get_schedule_or_404(db, request_data.schedule_id)
    if schedule.TrangThai == CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể xin phép vắng cho buổi học đã hủy.",
        )
    session_start = datetime.combine(schedule.NgayHoc, schedule.GioBatDau)
    if session_start <= business_now_naive():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chỉ có thể gửi đơn xin phép trước giờ bắt đầu buổi học.",
        )
    _ensure_attendance_scope(db, schedule, current_user)
    roster_ids = {
        student.NguoiDungId for student in _attendance_roster(db, schedule)
    }
    if current_user.NguoiDungId not in roster_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không thuộc lớp tại ngày diễn ra buổi học này.",
        )
    existing = (
        db.query(SessionAbsenceRequest)
        .filter(
            SessionAbsenceRequest.LichHocId == schedule.LichHocId,
            SessionAbsenceRequest.HocVienId == current_user.NguoiDungId,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bạn đã gửi đơn xin phép cho buổi học này.",
        )

    evidence_path = None
    evidence_name = None
    evidence_mime = None
    evidence_size = None
    if evidence is not None:
        contents, original_name, content_type = evidence
        extension = Path(original_name).suffix.lower()
        valid_type = EVIDENCE_TYPES.get(extension)
        if (
            valid_type is None
            or content_type.lower() != valid_type[0]
            or not valid_type[1](contents)
        ):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Minh chứng phải là tệp PDF, PNG hoặc JPEG hợp lệ.",
            )
        evidence_name = f"{uuid4().hex}{extension}"
        evidence_path = evidence_name
        evidence_mime = valid_type[0]
        evidence_size = len(contents)
        EVIDENCE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        (EVIDENCE_DIRECTORY / evidence_name).write_bytes(contents)

    item = SessionAbsenceRequest(
        LichHocId=schedule.LichHocId,
        HocVienId=current_user.NguoiDungId,
        LyDo=request_data.reason,
        TepMinhChungPath=evidence_path,
        TepMinhChungTen=Path(evidence[1]).name if evidence else None,
        TepMinhChungMime=evidence_mime,
        TepMinhChungKichThuoc=evidence_size,
        TrangThai="Chờ duyệt",
        NgayTao=business_now_naive(),
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if evidence_name:
            (EVIDENCE_DIRECTORY / evidence_name).unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bạn đã gửi đơn xin phép cho buổi học này.",
        ) from error
    except Exception:
        db.rollback()
        if evidence_name:
            (EVIDENCE_DIRECTORY / evidence_name).unlink(missing_ok=True)
        raise
    db.refresh(item)
    return _request_payload(db, item)


@router.get(
    "/absence-requests",
    dependencies=[Depends(require_permission("ATTENDANCE_VIEW"))],
)
def list_absence_requests(
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(SessionAbsenceRequest).order_by(SessionAbsenceRequest.NgayTao.desc())
    if STUDENT_ROLE_ID in user_role_ids(db, current_user.NguoiDungId):
        query = query.filter(SessionAbsenceRequest.HocVienId == current_user.NguoiDungId)
    else:
        role_ids = user_role_ids(db, current_user.NguoiDungId)
        if not has_schedule_wide_scope(db, current_user.NguoiDungId, role_ids):
            if not role_ids.intersection(TEACHING_ROLE_IDS):
                return []
            query = query.join(
                LichHoc,
                LichHoc.LichHocId == SessionAbsenceRequest.LichHocId,
            ).filter(LichHoc.GiangVienId == current_user.NguoiDungId)
    return [_request_payload(db, item) for item in query.all()]


@router.post(
    "/absence-requests",
    status_code=status.HTTP_201_CREATED,
)
def create_absence_request(
    request: AbsenceRequestWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _create_absence_request(db, request, current_user)


@router.post(
    "/absence-requests/with-evidence",
    status_code=status.HTTP_201_CREATED,
)
def create_absence_request_with_evidence(
    schedule_id: int = Form(alias="scheduleId", gt=0),
    reason: str = Form(min_length=1, max_length=1000),
    file: UploadFile = File(),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    contents = file.file.read(MAX_EVIDENCE_SIZE + 1)
    if len(contents) > MAX_EVIDENCE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Tệp minh chứng không được vượt quá 5 MB.",
        )
    request_data = AbsenceRequestWrite(
        scheduleId=schedule_id,
        reason=reason,
    )
    return _create_absence_request(
        db,
        request_data,
        current_user,
        evidence=(contents, file.filename or "", file.content_type or ""),
    )


@router.post(
    "/absence-requests/{request_id}/decision",
    dependencies=[Depends(require_permission("ATTENDANCE_UPDATE"))],
)
def decide_absence_request(
    request_id: int,
    decision: AbsenceRequestDecision,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _acquire_schedule_write_lock(db)
    item = _get_absence_request_or_404(db, request_id)
    if item.TrangThai != "Chờ duyệt":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Đơn xin phép này đã được xử lý.",
        )
    schedule = _get_schedule_or_404(db, item.LichHocId)
    _ensure_absence_review_scope(db, schedule, current_user)
    if schedule.TrangThai == CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể xử lý đơn cho buổi học đã hủy.",
        )

    now = business_now_naive()

    item.TrangThai = (
        "Đã duyệt" if decision.decision == "approved" else "Từ chối"
    )
    item.LyDoDuyet = decision.reason
    item.NguoiDuyetId = current_user.NguoiDungId
    item.ThoiDiemDuyet = now
    if decision.decision == "approved":
        attendance = (
            db.query(DiemDanhBuoiHoc)
            .filter(
                DiemDanhBuoiHoc.LichHocId == schedule.LichHocId,
                DiemDanhBuoiHoc.HocVienId == item.HocVienId,
            )
            .first()
        )
        old_status = attendance.TrangThai if attendance else None
        if attendance is None:
            attendance = DiemDanhBuoiHoc(
                LichHocId=schedule.LichHocId,
                HocVienId=item.HocVienId,
                NguoiCapNhatId=current_user.NguoiDungId,
                NgayCapNhat=now,
            )
            db.add(attendance)
        attendance.TrangThai = "Vắng có phép"
        attendance.GhiChu = decision.reason
        attendance.NguoiCapNhatId = current_user.NguoiDungId
        attendance.NgayCapNhat = now
        db.add(
            SessionAttendanceAudit(
                LichHocId=schedule.LichHocId,
                HocVienId=item.HocVienId,
                TrangThaiCu=old_status,
                TrangThaiMoi="Vắng có phép",
                GhiChu=decision.reason,
                NguoiThucHienId=current_user.NguoiDungId,
                ThoiDiem=now,
            )
        )

    class_record = (
        db.query(LopHoc)
        .filter(LopHoc.LopHocId == schedule.LopHocId)
        .first()
    )
    class_label = class_record.MaLop if class_record else "lớp học"
    db.add(
        SessionAttendanceNotification(
            RequestId=item.RequestId,
            NguoiNhanId=item.HocVienId,
            NoiDung=(
                f"Đơn xin phép vắng buổi {class_label} ngày "
                f"{schedule.NgayHoc.isoformat()} đã được duyệt."
                if decision.decision == "approved"
                else f"Đơn xin phép vắng buổi {class_label} ngày "
                f"{schedule.NgayHoc.isoformat()} đã bị từ chối."
            )
            + f" Lý do: {decision.reason}",
            ThoiDiem=now,
        )
    )
    db.commit()
    db.refresh(item)
    if decision.decision == "approved":
        try:
            student = db.query(NguoiDung).filter(
                NguoiDung.NguoiDungId == item.HocVienId
            ).first()
            subject = (
                db.query(MonHoc)
                .filter(MonHoc.MonHocId == schedule.MonHocId)
                .first()
            )
            if student is None or not student.Email:
                raise RuntimeError("Không tìm thấy email học viên.")
            send_absence_request_approved_email(
                student.Email,
                student.HoTen,
                class_label,
                subject.TenMonHoc if subject else "Buổi học",
                schedule.NgayHoc.isoformat(),
                schedule.GioBatDau.strftime("%H:%M"),
                schedule.GioKetThuc.strftime("%H:%M"),
                decision.reason,
            )
        except Exception:
            logger.exception(
                "Could not email approval for absence request %s to student %s",
                item.RequestId,
                item.HocVienId,
            )
    return _request_payload(db, item)


@router.get(
    "/absence-requests/{request_id}/evidence",
    dependencies=[Depends(require_permission("ATTENDANCE_VIEW"))],
)
def download_absence_evidence(
    request_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = _get_absence_request_or_404(db, request_id)
    schedule = _get_schedule_or_404(db, item.LichHocId)
    if item.HocVienId != current_user.NguoiDungId:
        _ensure_absence_review_scope(db, schedule, current_user)
    if not item.TepMinhChungPath:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Đơn này không có tệp minh chứng.",
        )
    file_path = (EVIDENCE_DIRECTORY / Path(item.TepMinhChungPath).name).resolve()
    if file_path.parent != EVIDENCE_DIRECTORY.resolve() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy tệp minh chứng.",
        )
    return FileResponse(
        file_path,
        media_type=item.TepMinhChungMime or "application/octet-stream",
        filename=item.TepMinhChungTen or "absence-evidence",
    )


@router.get(
    "/notifications",
    dependencies=[Depends(require_permission("ATTENDANCE_VIEW"))],
)
def list_attendance_notifications(
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = (
        db.query(SessionAttendanceNotification)
        .filter(
            SessionAttendanceNotification.NguoiNhanId == current_user.NguoiDungId
        )
        .order_by(SessionAttendanceNotification.ThoiDiem.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": item.NotificationId,
            "type": "absence_request",
            "title": "Kết quả đơn xin phép vắng",
            "message": item.NoiDung,
            "at": item.ThoiDiem.isoformat(),
            "read": item.DaDoc,
        }
        for item in items
    ]


@router.get(
    "/notifications/approved-alert",
    dependencies=[Depends(require_permission("ATTENDANCE_VIEW"))],
)
def get_pending_approved_absence_alert(
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _student_only(db, current_user)
    notification = (
        db.query(SessionAttendanceNotification)
        .join(
            SessionAbsenceRequest,
            SessionAbsenceRequest.RequestId
            == SessionAttendanceNotification.RequestId,
        )
        .filter(
            SessionAttendanceNotification.NguoiNhanId
            == current_user.NguoiDungId,
            SessionAttendanceNotification.DaDoc.is_(False),
            SessionAbsenceRequest.TrangThai == "Đã duyệt",
        )
        .order_by(SessionAttendanceNotification.ThoiDiem.asc())
        .first()
    )
    if notification is None:
        return None
    return {
        "id": notification.NotificationId,
        "message": notification.NoiDung,
    }


@router.post(
    "/notifications/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("ATTENDANCE_VIEW"))],
)
def mark_attendance_notification_read(
    notification_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _student_only(db, current_user)
    notification = (
        db.query(SessionAttendanceNotification)
        .filter(
            SessionAttendanceNotification.NotificationId == notification_id,
            SessionAttendanceNotification.NguoiNhanId
            == current_user.NguoiDungId,
        )
        .first()
    )
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thông báo.",
        )
    notification.DaDoc = True
    db.commit()


@router.get(
    "/my-history",
    dependencies=[Depends(require_permission("ATTENDANCE_VIEW"))],
)
def get_my_attendance_history(
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _student_only(db, current_user)
    rows = (
        db.query(DiemDanhBuoiHoc, LichHoc, LopHoc)
        .join(LichHoc, LichHoc.LichHocId == DiemDanhBuoiHoc.LichHocId)
        .join(LopHoc, LopHoc.LopHocId == LichHoc.LopHocId)
        .filter(DiemDanhBuoiHoc.HocVienId == current_user.NguoiDungId)
        .order_by(LichHoc.NgayHoc.desc(), LichHoc.GioBatDau.desc())
        .all()
    )
    records = [
        {
            "classId": class_record.LopHocId,
            "classCode": class_record.MaLop,
            "className": class_record.TenLop,
            "date": schedule.NgayHoc.isoformat(),
            "status": attendance.TrangThai,
            "reason": attendance.GhiChu,
        }
        for attendance, schedule, class_record in rows
    ]
    requests = (
        db.query(SessionAbsenceRequest)
        .filter(SessionAbsenceRequest.HocVienId == current_user.NguoiDungId)
        .order_by(SessionAbsenceRequest.NgayTao.desc())
        .all()
    )
    notifications = list_attendance_notifications(current_user, db)
    return {
        "records": records,
        "requests": [_request_payload(db, item) for item in requests],
        "warning": None,
        "notifications": notifications,
    }


@audit_router.get(
    "/schedules/{schedule_id}/audit",
    dependencies=[Depends(require_permission("ATTENDANCE_VIEW"))],
)
def get_attendance_audit(
    schedule_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = _get_schedule_or_404(db, schedule_id)
    _ensure_attendance_scope(db, schedule, current_user)
    if STUDENT_ROLE_ID in user_role_ids(db, current_user.NguoiDungId):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Học viên không được xem nhật ký chỉnh sửa điểm danh.",
        )
    items = (
        db.query(SessionAttendanceAudit)
        .filter(SessionAttendanceAudit.LichHocId == schedule_id)
        .order_by(SessionAttendanceAudit.ThoiDiem.desc())
        .all()
    )
    actor_ids = {item.NguoiThucHienId for item in items}
    student_ids = {item.HocVienId for item in items}
    names = {
        user.NguoiDungId: user.HoTen
        for user in db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId.in_(actor_ids | student_ids))
        .all()
    } if actor_ids or student_ids else {}
    return [
        {
            "at": item.ThoiDiem.isoformat(),
            "student": names.get(item.HocVienId),
            "action": "Tạo điểm danh" if item.TrangThaiCu is None else "Cập nhật",
            "old": item.TrangThaiCu,
            "new": item.TrangThaiMoi,
            "reason": item.GhiChu,
            "actor": names.get(item.NguoiThucHienId),
        }
        for item in items
    ]
