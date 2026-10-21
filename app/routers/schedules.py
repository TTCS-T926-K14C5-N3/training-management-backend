import json
import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import Date as SQLDate
from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.database import SessionLocal, get_db
from app.models.lich_hoc import LichHoc, LichHocLichSu
from app.models.lich_hoc_thong_bao import LichHocThongBao
from app.models.diem_danh import DiemDanh
from app.models.diem_danh_buoi_hoc import (
    DiemDanhBuoiHoc,
    DiemDanhBuoiHocLichSu,
)
from app.models.absence_request import (
    AbsenceRequest,
    AttendanceAudit,
    AttendanceNotification,
)
from app.models.curriculum import ProgramSession, ProgramSubject
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.student_enrollment_action import StudentEnrollmentAction
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.mon_hoc import MonHoc
from app.models.program_subject import BuoiHoc, ChuongTrinhMonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.quyen import Quyen
from app.models.phong_hoc import PhongHoc
from app.models.vai_tro_quyen import VaiTroQuyen
from app.schemas.lich_hoc import (
    DiemDanhBuoiHocWrite,
    DiemDanhWrite,
    LichHocCancel,
    LichHocGenerate,
    LichHocRepeatWrite,
    LichHocWrite,
)
from app.services.academic_service import (
    STUDENT_ROLE_ID,
    TEACHING_ROLE_IDS,
    accessible_classes,
    can_access_class,
    ensure_active_instructor,
    user_role_ids,
)
from app.services.schedule_notifications import (
    process_schedule_notifications,
    queue_schedule_notifications,
)
from app.services.business_time import business_now_naive


router = APIRouter(prefix="/academic", tags=["Schedule management"])
SCHEDULED = "Đã lên lịch"
CANCELLED = "Đã hủy"
logger = logging.getLogger(__name__)


def _deliver_schedule_notifications(event_id: str) -> None:
    db = SessionLocal()
    try:
        process_schedule_notifications(db, event_id=event_id)
    except Exception:
        logger.exception(
            "Failed to process schedule notification event %s",
            event_id,
        )
    finally:
        db.close()


def _schedule_notification_delivery(
    event_id: str | None,
    background_tasks: BackgroundTasks | None,
    db: Session,
) -> None:
    if event_id is None:
        return
    if background_tasks is None:
        process_schedule_notifications(db, event_id=event_id)
    else:
        background_tasks.add_task(_deliver_schedule_notifications, event_id)


def _commit(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from error


def _acquire_schedule_write_lock(db: Session) -> None:
    if db.get_bind().dialect.name != "mssql":
        return
    result = db.execute(
        text(
            """
            DECLARE @lock_result int;
            EXEC @lock_result = sys.sp_getapplock
                @Resource = :resource,
                @LockMode = 'Exclusive',
                @LockOwner = 'Transaction',
                @LockTimeout = 15000;
            SELECT @lock_result;
            """
        ),
        {"resource": "academic-schedule-writes"},
    ).scalar_one()
    if result < 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hệ thống đang xử lý lịch học khác. Vui lòng thử lại.",
        )


def _get_schedule_or_404(db: Session, schedule_id: int) -> LichHoc:
    schedule = (
        db.query(LichHoc)
        .filter(LichHoc.LichHocId == schedule_id)
        .first()
    )
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy buổi học.",
        )
    return schedule


def _get_class_or_404(db: Session, class_id: int) -> LopHoc:
    class_record = db.query(LopHoc).filter(LopHoc.LopHocId == class_id).first()
    if class_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy lớp học.",
        )
    if class_record.TrangThai not in {"Chuẩn bị", "Đang học", "Đang hoạt động"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể xếp lịch cho lớp đã kết thúc, hủy hoặc lưu trữ.",
        )
    return class_record


def _attendance_roster(db: Session, schedule: LichHoc) -> list[NguoiDung]:
    next_day = schedule.NgayHoc + timedelta(days=1)
    enrollments = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == schedule.LopHocId,
            LopHocHocVien.NgayThamGia < datetime.combine(next_day, time.min),
        )
        .all()
    )
    enrolled_ids = {item.HocVienId for item in enrollments}
    ended_ids = {
        student_id
        for (student_id,) in db.query(StudentEnrollmentAction.HocVienId)
        .filter(
            StudentEnrollmentAction.LopHocId == schedule.LopHocId,
            StudentEnrollmentAction.NgayHieuLuc <= schedule.NgayHoc,
        )
        .distinct()
        .all()
    }
    active_ids = enrolled_ids - ended_ids
    if not active_ids:
        return []
    return (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId.in_(active_ids))
        .order_by(NguoiDung.HoTen)
        .all()
    )


def _attendance_summary(db: Session, schedule: LichHoc) -> str | None:
    if schedule.TrangThai == CANCELLED:
        return None
    roster = _attendance_roster(db, schedule)
    if not roster:
        return "Không có học viên"
    roster_ids = [student.NguoiDungId for student in roster]
    recorded_ids = {
        student_id
        for (student_id,) in db.query(DiemDanh.HocVienId)
        .filter(
            DiemDanh.LichHocId == schedule.LichHocId,
            DiemDanh.HocVienId.in_(roster_ids),
        )
        .all()
    }
    recorded_ids.update(
        student_id
        for (student_id,) in db.query(DiemDanhBuoiHoc.HocVienId)
        .filter(
            DiemDanhBuoiHoc.LichHocId == schedule.LichHocId,
            DiemDanhBuoiHoc.HocVienId.in_(roster_ids),
        )
        .all()
    )
    recorded_count = len(recorded_ids)
    if recorded_count == 0:
        return "Chưa điểm danh"
    return f"{recorded_count}/{len(roster)} đã điểm danh"


def _schedule_payload(db: Session, schedule: LichHoc) -> dict:
    class_record = (
        db.query(LopHoc).filter(LopHoc.LopHocId == schedule.LopHocId).first()
    )
    subject = db.query(MonHoc).filter(MonHoc.MonHocId == schedule.MonHocId).first()
    buoi_hoc = (
        db.query(BuoiHoc).filter(BuoiHoc.BuoiHocId == schedule.BuoiHocId).first()
        if schedule.BuoiHocId is not None
        else None
    )
    teacher = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == schedule.GiangVienId)
        .first()
    )
    bai_hoc = (
        db.query(ProgramSession)
        .filter(ProgramSession.BuoiHocId == schedule.BaiHocId)
        .first()
        if schedule.BaiHocId is not None
        else None
    )
    room = (
        db.query(PhongHoc)
        .filter(PhongHoc.PhongHocId == schedule.PhongHocId)
        .first()
        if schedule.PhongHocId is not None
        else None
    )
    now = business_now_naive()
    starts_at = datetime.combine(schedule.NgayHoc, schedule.GioBatDau)
    ends_at = datetime.combine(schedule.NgayHoc, schedule.GioKetThuc)
    if schedule.TrangThai == SCHEDULED and starts_at <= now < ends_at:
        state = "Đang diễn ra"
    elif schedule.TrangThai == SCHEDULED and ends_at <= now:
        state = "Đã diễn ra"
    else:
        state = schedule.TrangThai
    return {
        "lichHocId": schedule.LichHocId,
        "maBuoiHoc": f"BH-{schedule.LichHocId:06d}",
        "lopHocId": schedule.LopHocId,
        "maLop": class_record.MaLop if class_record else None,
        "tenLop": class_record.TenLop if class_record else None,
        "monHocId": schedule.MonHocId,
        "tenMonHoc": subject.TenMonHoc if subject else None,
        "buoiHocId": schedule.BuoiHocId,
        "baiHocId": schedule.BaiHocId,
        "soThuTuBaiHoc": (
            bai_hoc.SoThuTu if bai_hoc else buoi_hoc.SoThuTu if buoi_hoc else None
        ),
        "chuDeBaiHoc": (
            bai_hoc.ChuDe if bai_hoc else buoi_hoc.ChuDe if buoi_hoc else None
        ),
        "ngayHoc": schedule.NgayHoc.isoformat(),
        "gioBatDau": schedule.GioBatDau.strftime("%H:%M"),
        "gioKetThuc": schedule.GioKetThuc.strftime("%H:%M"),
        "phongHocId": schedule.PhongHocId,
        "maPhong": room.MaPhong if room else None,
        "tenPhong": room.TenPhong if room else None,
        "giangVienId": schedule.GiangVienId,
        "giangVienTen": teacher.HoTen if teacher else None,
        "trangThai": state,
        "coTheChinhSua": state == SCHEDULED,
        "coTheHuy": state == SCHEDULED,
        "trangThaiDiemDanh": _attendance_summary(db, schedule),
        "lyDoHuy": schedule.LyDoHuy,
        "ngayTao": schedule.NgayTao.isoformat(),
        "ngayCapNhat": schedule.NgayCapNhat.isoformat(),
        "ngayHuy": schedule.NgayHuy.isoformat() if schedule.NgayHuy else None,
    }


def _snapshot(db: Session, schedule: LichHoc) -> str:
    return json.dumps(
        _schedule_payload(db, schedule),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _accessible_schedule_query(
    db: Session,
    current_user: NguoiDung,
    include_inactive_classes: bool = False,
):
    class_ids = {
        item.LopHocId
        for item in accessible_classes(
            db,
            current_user,
            include_inactive=include_inactive_classes,
        )
    }
    query = db.query(LichHoc).filter(LichHoc.LopHocId.in_(class_ids))
    if not class_ids:
        return query

    role_ids = {
        role_id
        for (role_id,) in db.query(NguoiDungVaiTro.VaiTroId)
        .filter(NguoiDungVaiTro.NguoiDungId == current_user.NguoiDungId)
        .all()
    }
    if STUDENT_ROLE_ID in role_ids:
        enrollment_exists = exists().where(
            and_(
                LopHocHocVien.LopHocId == LichHoc.LopHocId,
                LopHocHocVien.HocVienId == current_user.NguoiDungId,
                func.cast(LopHocHocVien.NgayThamGia, SQLDate)
                <= LichHoc.NgayHoc,
            )
        )
        enrollment_ended = exists().where(
            and_(
                StudentEnrollmentAction.HocVienId == current_user.NguoiDungId,
                StudentEnrollmentAction.LopHocId == LichHoc.LopHocId,
                StudentEnrollmentAction.NgayHieuLuc <= LichHoc.NgayHoc,
            )
        )
        query = query.filter(enrollment_exists, ~enrollment_ended)
    return query


def _validate_class_subject(
    db: Session,
    class_record: LopHoc,
    subject_id: int,
) -> None:
    assigned = (
        db.query(LopHocMonHoc.LopHocId)
        .filter(
            LopHocMonHoc.LopHocId == class_record.LopHocId,
            LopHocMonHoc.MonHocId == subject_id,
        )
        .first()
    )
    if assigned is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Môn học chưa được gán cho lớp này.",
        )


def _validate_room(db: Session, room_id: int) -> None:
    room = db.query(PhongHoc).filter(PhongHoc.PhongHocId == room_id).first()
    if room is None or room.TrangThai != "Đang hoạt động":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Phòng học không tồn tại hoặc đã ngừng hoạt động.",
        )


def _instructor_roles(db: Session, class_id: int, subject_id: int) -> dict[int, str]:
    return {
        instructor_id: role
        for instructor_id, role in db.query(
            LopHocMonHocGiangVien.GiangVienId,
            LopHocMonHocGiangVien.VaiTro,
        )
        .filter(
            LopHocMonHocGiangVien.LopHocId == class_id,
            LopHocMonHocGiangVien.MonHocId == subject_id,
        )
        .all()
    }


def _online_room_key(class_record: LopHoc | None) -> str | None:
    if (
        class_record is None
        or class_record.HinhThuc not in {"Trực tuyến", "Kết hợp"}
        or not class_record.LinkTrucTuyen
    ):
        return None
    return class_record.LinkTrucTuyen.strip().rstrip("/") or None


def _find_conflicts(
    db: Session,
    request: LichHocWrite,
    exclude_schedule_id: int | None = None,
) -> list[dict]:
    query = db.query(LichHoc).filter(
        LichHoc.NgayHoc == request.ngay_hoc,
        LichHoc.TrangThai == SCHEDULED,
        LichHoc.GioBatDau < request.gio_ket_thuc,
        LichHoc.GioKetThuc > request.gio_bat_dau,
    )
    if exclude_schedule_id is not None:
        query = query.filter(LichHoc.LichHocId != exclude_schedule_id)

    overlaps = query.order_by(LichHoc.GioBatDau).all()
    conflicts = []
    request_class = (
        db.query(LopHoc).filter(LopHoc.LopHocId == request.lop_hoc_id).first()
    )
    request_online_room = _online_room_key(request_class)
    request_roles = _instructor_roles(db, request.lop_hoc_id, request.mon_hoc_id)
    request_instructors = set(request_roles) | {request.giang_vien_id}
    for existing in overlaps:
        labels = []
        existing_roles = _instructor_roles(db, existing.LopHocId, existing.MonHocId)
        existing_instructors = set(existing_roles) | {existing.GiangVienId}
        class_record = (
            db.query(LopHoc)
            .filter(LopHoc.LopHocId == existing.LopHocId)
            .first()
        )
        same_online_room = (
            request_online_room is not None
            and request_online_room == _online_room_key(class_record)
        )
        for instructor_id in sorted(request_instructors & existing_instructors):
            teacher = (
                db.query(NguoiDung)
                .filter(NguoiDung.NguoiDungId == instructor_id)
                .first()
            )
            teacher_conflict = {
                "loai": "giangVien",
                "ten": teacher.HoTen if teacher else None,
            }
            role = existing_roles.get(instructor_id) or request_roles.get(instructor_id)
            if role:
                teacher_conflict["vaiTro"] = role
            labels.append(teacher_conflict)
        if existing.PhongHocId == request.phong_hoc_id:
            room = (
                db.query(PhongHoc)
                .filter(PhongHoc.PhongHocId == request.phong_hoc_id)
                .first()
            )
            labels.append(
                {
                    "loai": "phongHoc",
                    "ten": room.TenPhong if room else None,
                    "maPhong": room.MaPhong if room else None,
                }
            )
        if same_online_room:
            labels.append(
                {
                    "loai": "phongHoc",
                    "ten": "Phòng trực tuyến",
                    "maPhong": "Trực tuyến",
                    "linkTrucTuyen": class_record.LinkTrucTuyen,
                }
            )
        for label in labels:
            conflicts.append(
                {
                    **label,
                    "ngay": existing.NgayHoc.isoformat(),
                    "gioBatDau": existing.GioBatDau.strftime("%H:%M"),
                    "gioKetThuc": existing.GioKetThuc.strftime("%H:%M"),
                    "lichHocId": existing.LichHocId,
                    "maBuoiHoc": f"BH-{existing.LichHocId:06d}",
                    "maLop": class_record.MaLop if class_record else None,
                    "tenLop": class_record.TenLop if class_record else None,
                }
            )
    return conflicts


def _ensure_not_conflicting(
    conflicts: list[dict],
    request: LichHocWrite,
    current_user: NguoiDung,
    db: Session,
) -> None:
    if not conflicts:
        return
    can_override = _can_override_conflicts(db, current_user)
    if request.xac_nhan_trung_lich and can_override:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": "Lịch học bị trùng với buổi học đã được xếp.",
            "conflicts": conflicts,
            "canOverride": can_override,
        },
    )


def _repeat_schedules(
    request: LichHocRepeatWrite,
    current_user: NguoiDung,
    db: Session,
) -> tuple[LopHoc, list[dict]]:
    class_record = _get_class_or_404(db, request.lop_hoc_id)
    if not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )
    _validate_class_subject(db, class_record, request.mon_hoc_id)
    try:
        ensure_active_instructor(db, request.giang_vien_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    _validate_room(db, request.phong_hoc_id)

    lessons = _program_lessons(db, class_record, request.mon_hoc_id)
    if lessons and request.so_buoi > len(lessons):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Số buổi vượt quá số bài học đã khai báo cho môn này.",
        )

    holidays = set(request.ngay_nghi)
    sessions: list[dict] = []
    current_day = request.ngay_bat_dau
    scan_limit = current_day + timedelta(days=365 * 5)
    while len(sessions) < request.so_buoi and current_day <= scan_limit:
        if current_day.isoweekday() in request.thu_trong_tuan and current_day not in holidays:
            lesson = lessons[len(sessions)] if lessons else None
            schedule_request = LichHocWrite(
                lopHocId=request.lop_hoc_id,
                monHocId=request.mon_hoc_id,
                baiHocId=lesson.BuoiHocId if lesson else None,
                ngayHoc=current_day,
                gioBatDau=request.gio_bat_dau,
                gioKetThuc=request.gio_ket_thuc,
                phongHocId=request.phong_hoc_id,
                giangVienId=request.giang_vien_id,
                ghiDeXungDot=request.ghi_de_xung_dot,
                lyDoGhiDe=request.ly_do_ghi_de,
            )
            sessions.append(
                {
                    "request": schedule_request,
                    "lesson": lesson,
                    "conflicts": _find_conflicts(db, schedule_request),
                }
            )
        current_day += timedelta(days=1)

    if len(sessions) != request.so_buoi:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Không thể sinh đủ buổi học trong giới hạn thời gian.",
        )
    return class_record, sessions


def _repeat_preview_payload(sessions: list[dict]) -> dict:
    items = []
    for index, item in enumerate(sessions, start=1):
        request = item["request"]
        lesson = item["lesson"]
        items.append(
            {
                "stt": index,
                "ngayHoc": request.ngay_hoc.isoformat(),
                "gioBatDau": request.gio_bat_dau.strftime("%H:%M"),
                "gioKetThuc": request.gio_ket_thuc.strftime("%H:%M"),
                "baiHocId": lesson.BuoiHocId if lesson else None,
                "soThuTuBaiHoc": lesson.SoThuTu if lesson else None,
                "chuDeBaiHoc": lesson.ChuDe if lesson else None,
                "xungDot": item["conflicts"],
            }
        )
    return {
        "buoiHocs": items,
        "soBuoi": len(items),
        "coXungDot": any(item["xungDot"] for item in items),
    }


def _can_override_conflicts(db: Session, user: NguoiDung) -> bool:
    return (
        db.query(Quyen.QuyenId)
        .join(VaiTroQuyen, VaiTroQuyen.QuyenId == Quyen.QuyenId)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.VaiTroId == VaiTroQuyen.VaiTroId,
        )
        .filter(
            NguoiDungVaiTro.NguoiDungId == user.NguoiDungId,
            Quyen.MaQuyen == "SCHEDULE_OVERRIDE",
        )
        .first()
        is not None
    )


def _validate_lesson(
    db: Session,
    class_record: LopHoc,
    subject_id: int,
    lesson_id: int | None,
) -> None:
    if lesson_id is None:
        return
    lesson = (
        db.query(ProgramSession)
        .join(
            ProgramSubject,
            ProgramSubject.ChuongTrinhMonHocId
            == ProgramSession.ChuongTrinhMonHocId,
        )
        .filter(
            ProgramSession.BuoiHocId == lesson_id,
            ProgramSubject.MonHocId == subject_id,
            ProgramSubject.ChuongTrinhId == class_record.ChuongTrinhId,
        )
        .first()
    )
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Bài học không thuộc môn học và chương trình của lớp.",
        )


def _program_lessons(
    db: Session,
    class_record: LopHoc,
    subject_id: int,
) -> list[ProgramSession]:
    if class_record.ChuongTrinhId is None:
        return []
    return (
        db.query(ProgramSession)
        .join(
            ProgramSubject,
            ProgramSubject.ChuongTrinhMonHocId
            == ProgramSession.ChuongTrinhMonHocId,
        )
        .filter(
            ProgramSubject.ChuongTrinhId == class_record.ChuongTrinhId,
            ProgramSubject.MonHocId == subject_id,
        )
        .order_by(ProgramSession.SoThuTu, ProgramSession.BuoiHocId)
        .all()
    )


def _get_subject_lessons(
    db: Session,
    class_record: LopHoc,
    subject_id: int,
) -> list[BuoiHoc]:
    if class_record.ChuongTrinhId is None:
        return []
    association = (
        db.query(ChuongTrinhMonHoc)
        .filter(
            ChuongTrinhMonHoc.ChuongTrinhId == class_record.ChuongTrinhId,
            ChuongTrinhMonHoc.MonHocId == subject_id,
        )
        .first()
    )
    if association is None:
        return []
    return (
        db.query(BuoiHoc)
        .filter(BuoiHoc.ChuongTrinhMonHocId == association.ChuongTrinhMonHocId)
        .order_by(BuoiHoc.SoThuTu)
        .all()
    )


def _validate_buoi_hoc(
    db: Session,
    class_record: LopHoc,
    subject_id: int,
    lesson_id: int | None,
    exclude_schedule_id: int | None = None,
) -> None:
    if lesson_id is None:
        return
    lesson = (
        db.query(BuoiHoc)
        .join(
            ChuongTrinhMonHoc,
            ChuongTrinhMonHoc.ChuongTrinhMonHocId == BuoiHoc.ChuongTrinhMonHocId,
        )
        .filter(
            BuoiHoc.BuoiHocId == lesson_id,
            ChuongTrinhMonHoc.ChuongTrinhId == class_record.ChuongTrinhId,
            ChuongTrinhMonHoc.MonHocId == subject_id,
        )
        .first()
    )
    if lesson is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Buổi học không thuộc môn học và chương trình của lớp.",
        )
    scheduled_query = db.query(LichHoc.LichHocId).filter(
        LichHoc.LopHocId == class_record.LopHocId,
        LichHoc.BuoiHocId == lesson_id,
        LichHoc.TrangThai == SCHEDULED,
    )
    if exclude_schedule_id is not None:
        scheduled_query = scheduled_query.filter(
            LichHoc.LichHocId != exclude_schedule_id
        )
    if scheduled_query.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Buổi học đã được xếp lịch cho lớp này.",
        )


def _ensure_schedule_writable(db: Session, schedule: LichHoc) -> None:
    has_attendance = (
        db.query(DiemDanh.DiemDanhId)
        .filter(DiemDanh.LichHocId == schedule.LichHocId)
        .first()
        is not None
    ) or (
        db.query(DiemDanhBuoiHoc.DiemDanhBuoiHocId)
        .filter(DiemDanhBuoiHoc.LichHocId == schedule.LichHocId)
        .first()
        is not None
    )
    if has_attendance:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể chỉnh sửa hoặc hủy buổi học đã có dữ liệu điểm danh.",
        )
    if schedule.TrangThai != SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chỉ có thể chỉnh sửa buổi học đang ở trạng thái đã lên lịch.",
        )
    if datetime.combine(schedule.NgayHoc, schedule.GioBatDau) <= business_now_naive():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Buổi học đã bắt đầu hoặc đã diễn ra và không thể chỉnh sửa lịch.",
        )


def _ensure_no_attendance(db: Session, schedule: LichHoc) -> None:
    has_attendance = (
        db.query(DiemDanh.DiemDanhId)
        .filter(DiemDanh.LichHocId == schedule.LichHocId)
        .first()
    ) or (
        db.query(DiemDanhBuoiHoc.DiemDanhBuoiHocId)
        .filter(DiemDanhBuoiHoc.LichHocId == schedule.LichHocId)
        .first()
    )
    if has_attendance:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể thay đổi buổi học đã có dữ liệu điểm danh.",
        )


@router.get(
    "/schedule-options",
    dependencies=[Depends(require_permission("SCHEDULE_CREATE"))],
)
def get_schedule_options(
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    classes = accessible_classes(db, current_user)
    class_options = []
    for class_record in classes:
        subjects = (
            db.query(MonHoc)
            .join(LopHocMonHoc, LopHocMonHoc.MonHocId == MonHoc.MonHocId)
            .filter(LopHocMonHoc.LopHocId == class_record.LopHocId)
            .order_by(MonHoc.MaMonHoc)
            .all()
        )
        class_options.append(
            {
                "lopHocId": class_record.LopHocId,
                "maLop": class_record.MaLop,
                "tenLop": class_record.TenLop,
                "giangVienId": class_record.GiangVienId,
                "phongHocId": class_record.PhongHocId,
                "monHocs": [
                    {
                        "monHocId": subject.MonHocId,
                        "maMonHoc": subject.MaMonHoc,
                        "tenMonHoc": subject.TenMonHoc,
                        "baiHocs": [
                            {
                                "baiHocId": lesson.BuoiHocId,
                                "soThuTu": lesson.SoThuTu,
                                "chuDe": lesson.ChuDe,
                            }
                            for lesson in _program_lessons(
                                db,
                                class_record,
                                subject.MonHocId,
                            )
                        ],
                        "buoiHocs": [
                            {
                                "buoiHocId": lesson.BuoiHocId,
                                "soThuTu": lesson.SoThuTu,
                                "chuDe": lesson.ChuDe,
                            }
                            for lesson in _get_subject_lessons(
                                db,
                                class_record,
                                subject.MonHocId,
                            )
                        ],
                    }
                    for subject in subjects
                ],
            }
        )

    teachers = (
        db.query(NguoiDung)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(
            NguoiDungVaiTro.VaiTroId.in_(TEACHING_ROLE_IDS),
            NguoiDung.TrangThai == "HoatDong",
        )
        .distinct()
        .order_by(NguoiDung.HoTen)
        .all()
    )
    rooms = (
        db.query(PhongHoc)
        .filter(PhongHoc.TrangThai == "Đang hoạt động")
        .order_by(PhongHoc.MaPhong)
        .all()
    )
    return {
        "lopHocs": class_options,
        "giangViens": [
            {
                "giangVienId": teacher.NguoiDungId,
                "hoTen": teacher.HoTen,
                "email": teacher.Email,
            }
            for teacher in teachers
        ],
        "phongHocs": [
            {
                "phongHocId": room.PhongHocId,
                "maPhong": room.MaPhong,
                "tenPhong": room.TenPhong,
                "trangThai": room.TrangThai,
            }
            for room in rooms
        ],
        "diemDanhDuocHoTro": True,
    }


@router.post(
    "/schedules/preview",
    dependencies=[Depends(require_permission("SCHEDULE_CREATE"))],
)
def preview_repeating_schedules(
    request: LichHocRepeatWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, sessions = _repeat_schedules(request, current_user, db)
    return _repeat_preview_payload(sessions)


@router.post(
    "/schedules/bulk",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("SCHEDULE_CREATE"))],
)
def create_repeating_schedules(
    request: LichHocRepeatWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _acquire_schedule_write_lock(db)
    _, sessions = _repeat_schedules(request, current_user, db)
    all_conflicts = [
        conflict
        for item in sessions
        for conflict in item["conflicts"]
    ]
    if all_conflicts:
        _ensure_not_conflicting(
            all_conflicts,
            sessions[0]["request"],
            current_user,
            db,
        )

    now = business_now_naive()
    schedules = []
    for item in sessions:
        schedule_request = item["request"]
        schedule = LichHoc(
            LopHocId=schedule_request.lop_hoc_id,
            MonHocId=schedule_request.mon_hoc_id,
            BaiHocId=schedule_request.bai_hoc_id,
            NgayHoc=schedule_request.ngay_hoc,
            GioBatDau=schedule_request.gio_bat_dau,
            GioKetThuc=schedule_request.gio_ket_thuc,
            PhongHocId=schedule_request.phong_hoc_id,
            GiangVienId=schedule_request.giang_vien_id,
            TrangThai=SCHEDULED,
            NgayTao=now,
            NguoiTaoId=current_user.NguoiDungId,
            NgayCapNhat=now,
            NguoiCapNhatId=current_user.NguoiDungId,
        )
        db.add(schedule)
        schedules.append((schedule, schedule_request.ly_do_ghi_de))

    try:
        db.flush()
        for schedule, reason in schedules:
            payload = _schedule_payload(db, schedule)
            db.add(
                LichHocLichSu(
                    LichHocId=schedule.LichHocId,
                    HanhDong="Tạo",
                    DuLieuMoi=json.dumps(payload, ensure_ascii=False),
                    LyDo=reason,
                    ThoiDiem=now,
                    NguoiThucHienId=current_user.NguoiDungId,
                )
            )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể lưu lịch lặp do dữ liệu bị trùng hoặc không hợp lệ.",
        ) from error
    return {
        "created": len(schedules),
        "items": [_schedule_payload(db, schedule) for schedule, _ in schedules],
    }


def _build_generated_plan(
    request: LichHocGenerate,
    current_user: NguoiDung,
    db: Session,
) -> tuple[LopHoc, list[BuoiHoc], list[date], list[date]]:
    if request.ngay_bat_dau < date.today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ngày bắt đầu phải từ hôm nay trở đi.",
        )
    class_record = _get_class_or_404(db, request.lop_hoc_id)
    if not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )
    _validate_class_subject(db, class_record, request.mon_hoc_id)
    try:
        ensure_active_instructor(db, request.giang_vien_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    _validate_room(db, request.phong_hoc_id)

    lessons = _get_subject_lessons(db, class_record, request.mon_hoc_id)
    if not lessons:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Môn học chưa có danh sách bài học trong chương trình đào tạo.",
        )
    if len(lessons) < request.so_buoi:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Môn học chỉ có {len(lessons)} bài học, không đủ {request.so_buoi} buổi cần xếp.",
        )
    lesson_ids = [item.BuoiHocId for item in lessons[: request.so_buoi]]
    if (
        db.query(LichHoc.LichHocId)
        .filter(
            LichHoc.LopHocId == request.lop_hoc_id,
            LichHoc.BuoiHocId.in_(lesson_ids),
            LichHoc.TrangThai == SCHEDULED,
        )
        .first()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Một hoặc nhiều bài học đã được xếp lịch cho lớp này.",
        )

    weekdays = set(request.thu_trong_tuan)
    holidays = set(request.ngay_nghi)
    dates: list[date] = []
    skipped_holidays: list[date] = []
    current_day = request.ngay_bat_dau
    deadline = request.ngay_bat_dau + timedelta(days=3650)
    now = datetime.now()
    while len(dates) < request.so_buoi and current_day <= deadline:
        if current_day.isoweekday() in weekdays:
            if current_day in holidays:
                skipped_holidays.append(current_day)
            elif current_day != now.date() or request.gio_bat_dau > now.time():
                dates.append(current_day)
        current_day += timedelta(days=1)
    if len(dates) != request.so_buoi:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Không thể tạo đủ số buổi trong thời hạn 10 năm.",
        )

    return class_record, lessons[: request.so_buoi], dates, skipped_holidays


@router.post(
    "/schedules/generate-preview",
    dependencies=[Depends(require_permission("SCHEDULE_CREATE"))],
)
def preview_generated_schedules(
    request: LichHocGenerate,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, lessons, dates, skipped_holidays = _build_generated_plan(
        request, current_user, db
    )
    sessions = []
    conflicts = []
    for lesson, scheduled_date in zip(lessons, dates):
        schedule_request = LichHocWrite(
            lopHocId=request.lop_hoc_id,
            monHocId=request.mon_hoc_id,
            buoiHocId=lesson.BuoiHocId,
            ngayHoc=scheduled_date,
            gioBatDau=request.gio_bat_dau,
            gioKetThuc=request.gio_ket_thuc,
            phongHocId=request.phong_hoc_id,
            giangVienId=request.giang_vien_id,
        )
        conflicts.extend(_find_conflicts(db, schedule_request))
        sessions.append(
            {
                "ngayHoc": scheduled_date.isoformat(),
                "buoiHocId": lesson.BuoiHocId,
                "soThuTu": lesson.SoThuTu,
                "chuDe": lesson.ChuDe,
            }
        )
    return {
        "sessions": sessions,
        "skippedHolidays": [item.isoformat() for item in skipped_holidays],
        "conflicts": conflicts,
    }


@router.post(
    "/schedules/generate",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("SCHEDULE_CREATE"))],
)
def generate_schedules(
    request: LichHocGenerate,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, lessons, dates, _ = _build_generated_plan(request, current_user, db)
    plan = [
        LichHocWrite(
            lopHocId=request.lop_hoc_id,
            monHocId=request.mon_hoc_id,
            buoiHocId=lesson.BuoiHocId,
            ngayHoc=scheduled_date,
            gioBatDau=request.gio_bat_dau,
            gioKetThuc=request.gio_ket_thuc,
            phongHocId=request.phong_hoc_id,
            giangVienId=request.giang_vien_id,
        )
        for lesson, scheduled_date in zip(lessons, dates)
    ]
    conflicts = [
        conflict
        for schedule_request in plan
        for conflict in _find_conflicts(db, schedule_request)
    ]
    _ensure_not_conflicting(
        conflicts,
        plan[0],
        current_user,
        db,
    )

    now = datetime.now()
    created = []
    for item in plan:
        schedule = LichHoc(
            LopHocId=item.lop_hoc_id,
            MonHocId=item.mon_hoc_id,
            BuoiHocId=item.buoi_hoc_id,
            NgayHoc=item.ngay_hoc,
            GioBatDau=item.gio_bat_dau,
            GioKetThuc=item.gio_ket_thuc,
            PhongHocId=item.phong_hoc_id,
            GiangVienId=item.giang_vien_id,
            TrangThai=SCHEDULED,
            NgayTao=now,
            NguoiTaoId=current_user.NguoiDungId,
            NgayCapNhat=now,
            NguoiCapNhatId=current_user.NguoiDungId,
        )
        db.add(schedule)
        try:
            db.flush()
        except IntegrityError as error:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Không thể lưu toàn bộ lịch do dữ liệu bị trùng hoặc thay đổi đồng thời.",
            ) from error
        payload = _schedule_payload(db, schedule)
        db.add(
            LichHocLichSu(
                LichHocId=schedule.LichHocId,
                HanhDong="Tạo",
                DuLieuMoi=json.dumps(payload, ensure_ascii=False),
                ThoiDiem=now,
                NguoiThucHienId=current_user.NguoiDungId,
            )
        )
        created.append(payload)

    _commit(db, "Không thể tạo lịch do dữ liệu bị trùng hoặc không hợp lệ.")
    return created


@router.get(
    "/schedules",
    dependencies=[Depends(require_permission("SCHEDULE_VIEW"))],
)
def list_schedules(
    start_date: date | None = Query(default=None, alias="startDate"),
    end_date: date | None = Query(default=None, alias="endDate"),
    status_filter: str | None = Query(default=None, alias="status"),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
    exclude_completed: bool = Query(default=False, alias="excludeCompleted"),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ngày bắt đầu lọc không được sau ngày kết thúc.",
        )
    query = _accessible_schedule_query(db, current_user)
    if exclude_completed:
        now = business_now_naive()
        query = query.filter(
            or_(
                LichHoc.TrangThai != SCHEDULED,
                LichHoc.NgayHoc > now.date(),
                and_(
                    LichHoc.NgayHoc == now.date(),
                    LichHoc.GioKetThuc > now.time(),
                ),
            )
        )
    if start_date:
        query = query.filter(LichHoc.NgayHoc >= start_date)
    if end_date:
        query = query.filter(LichHoc.NgayHoc <= end_date)
    if status_filter == CANCELLED:
        query = query.filter(LichHoc.TrangThai == CANCELLED)
    elif status_filter == SCHEDULED:
        now = business_now_naive()
        query = query.filter(
            LichHoc.TrangThai == SCHEDULED,
            or_(
                LichHoc.NgayHoc > now.date(),
                and_(
                    LichHoc.NgayHoc == now.date(),
                    LichHoc.GioBatDau > now.time(),
                ),
            ),
        )
    elif status_filter == "Đang diễn ra":
        now = business_now_naive()
        query = query.filter(
            LichHoc.TrangThai == SCHEDULED,
            LichHoc.NgayHoc == now.date(),
            LichHoc.GioBatDau <= now.time(),
            LichHoc.GioKetThuc > now.time(),
        )
    elif status_filter == "Đã diễn ra":
        now = business_now_naive()
        query = query.filter(
            LichHoc.TrangThai == SCHEDULED,
            or_(
                LichHoc.NgayHoc < now.date(),
                and_(
                    LichHoc.NgayHoc == now.date(),
                    LichHoc.GioKetThuc <= now.time(),
                ),
            ),
        )
    elif status_filter is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Trạng thái buổi học không hợp lệ.",
        )
    return [
        _schedule_payload(db, item)
        for item in query.order_by(LichHoc.NgayHoc, LichHoc.GioBatDau).all()
    ]


@router.get(
    "/schedules/completed",
    dependencies=[Depends(require_permission("SCHEDULE_VIEW"))],
)
def list_completed_schedules(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = business_now_naive()
    query = _accessible_schedule_query(
        db,
        current_user,
        include_inactive_classes=True,
    ).filter(
        LichHoc.TrangThai == SCHEDULED,
        or_(
            LichHoc.NgayHoc < now.date(),
            and_(
                LichHoc.NgayHoc == now.date(),
                LichHoc.GioKetThuc <= now.time(),
            ),
        ),
    )
    total = query.count()
    schedules = (
        query.order_by(LichHoc.NgayHoc.desc(), LichHoc.GioBatDau.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_schedule_payload(db, item) for item in schedules],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


@router.post(
    "/schedules/check-conflicts",
    dependencies=[Depends(require_permission("SCHEDULE_VIEW"))],
)
def check_schedule_conflicts(
    request: LichHocWrite,
    exclude_schedule_id: int | None = Query(
        default=None,
        alias="excludeScheduleId",
        gt=0,
    ),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    class_record = _get_class_or_404(db, request.lop_hoc_id)
    if not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )
    if exclude_schedule_id is not None:
        schedule = _get_schedule_or_404(db, exclude_schedule_id)
        existing_class = _get_class_or_404(db, schedule.LopHocId)
        if not can_access_class(db, current_user, existing_class):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
            )
        _ensure_schedule_writable(db, schedule)
        if (
            request.lop_hoc_id != schedule.LopHocId
            or request.mon_hoc_id != schedule.MonHocId
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Không được thay đổi lớp hoặc môn học của buổi học.",
            )
    _validate_class_subject(db, class_record, request.mon_hoc_id)
    _validate_lesson(
        db,
        class_record,
        request.mon_hoc_id,
        request.bai_hoc_id,
    )
    _validate_buoi_hoc(
        db,
        class_record,
        request.mon_hoc_id,
        request.buoi_hoc_id,
    )
    try:
        ensure_active_instructor(db, request.giang_vien_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    _validate_room(db, request.phong_hoc_id)
    conflicts = _find_conflicts(
        db,
        request,
        exclude_schedule_id=exclude_schedule_id,
    )
    return {
        "hasConflicts": bool(conflicts),
        "conflicts": conflicts,
        "canOverride": _can_override_conflicts(db, current_user),
    }


@router.post(
    "/schedules",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("SCHEDULE_CREATE"))],
)
def create_schedule(
    request: LichHocWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _acquire_schedule_write_lock(db)
    class_record = _get_class_or_404(db, request.lop_hoc_id)
    if not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )
    _validate_class_subject(db, class_record, request.mon_hoc_id)
    _validate_lesson(
        db,
        class_record,
        request.mon_hoc_id,
        request.bai_hoc_id,
    )
    try:
        ensure_active_instructor(db, request.giang_vien_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    _validate_room(db, request.phong_hoc_id)
    conflicts = _find_conflicts(db, request)
    _ensure_not_conflicting(conflicts, request, current_user, db)

    now = business_now_naive()
    schedule = LichHoc(
        LopHocId=request.lop_hoc_id,
        MonHocId=request.mon_hoc_id,
        BuoiHocId=request.buoi_hoc_id,
        BaiHocId=request.bai_hoc_id,
        NgayHoc=request.ngay_hoc,
        GioBatDau=request.gio_bat_dau,
        GioKetThuc=request.gio_ket_thuc,
        PhongHocId=request.phong_hoc_id,
        GiangVienId=request.giang_vien_id,
        TrangThai=SCHEDULED,
        NgayTao=now,
        NguoiTaoId=current_user.NguoiDungId,
        NgayCapNhat=now,
        NguoiCapNhatId=current_user.NguoiDungId,
    )
    db.add(schedule)
    db.flush()
    payload = _schedule_payload(db, schedule)
    db.add(
        LichHocLichSu(
            LichHocId=schedule.LichHocId,
            HanhDong="Tạo",
            DuLieuMoi=json.dumps(payload, ensure_ascii=False),
            LyDo=request.ly_do_ghi_de,
            ThoiDiem=now,
            NguoiThucHienId=current_user.NguoiDungId,
        )
    )
    _commit(db, "Không thể tạo buổi học do dữ liệu bị trùng hoặc không hợp lệ.")
    return payload


def update_schedule(
    schedule_id: int,
    request: LichHocWrite,
    current_user: NguoiDung,
    db: Session,
    background_tasks: BackgroundTasks | None = None,
):
    _acquire_schedule_write_lock(db)
    schedule = _get_schedule_or_404(db, schedule_id)
    class_record = _get_class_or_404(db, schedule.LopHocId)
    if not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )
    _ensure_schedule_writable(db, schedule)
    _ensure_no_attendance(db, schedule)
    if request.lop_hoc_id != schedule.LopHocId or request.mon_hoc_id != schedule.MonHocId:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Không được thay đổi lớp hoặc môn học của buổi học.",
        )
    _validate_class_subject(db, class_record, schedule.MonHocId)
    _validate_lesson(
        db,
        class_record,
        schedule.MonHocId,
        request.bai_hoc_id,
    )
    _validate_buoi_hoc(
        db,
        class_record,
        schedule.MonHocId,
        request.buoi_hoc_id,
        exclude_schedule_id=schedule_id,
    )
    try:
        ensure_active_instructor(db, request.giang_vien_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    _validate_room(db, request.phong_hoc_id)
    conflicts = _find_conflicts(
        db, request, exclude_schedule_id=schedule_id
    )
    _ensure_not_conflicting(conflicts, request, current_user, db)

    previous_teacher_id = schedule.GiangVienId
    previous_values = (
        schedule.NgayHoc,
        schedule.GioBatDau,
        schedule.GioKetThuc,
        schedule.PhongHocId,
        schedule.GiangVienId,
        schedule.BuoiHocId,
        schedule.BaiHocId,
    )
    updated_values = (
        request.ngay_hoc,
        request.gio_bat_dau,
        request.gio_ket_thuc,
        request.phong_hoc_id,
        request.giang_vien_id,
        request.buoi_hoc_id,
        request.bai_hoc_id,
    )
    schedule_changed = previous_values != updated_values
    previous_recipients = (
        {
            student.NguoiDungId
            for student in _attendance_roster(db, schedule)
        }
        if schedule_changed
        else set()
    )
    before = _snapshot(db, schedule)
    before_payload = json.loads(before)
    schedule.NgayHoc = request.ngay_hoc
    schedule.BuoiHocId = request.buoi_hoc_id
    schedule.GioBatDau = request.gio_bat_dau
    schedule.GioKetThuc = request.gio_ket_thuc
    schedule.PhongHocId = request.phong_hoc_id
    schedule.GiangVienId = request.giang_vien_id
    schedule.BaiHocId = request.bai_hoc_id
    schedule.NgayCapNhat = business_now_naive()
    schedule.NguoiCapNhatId = current_user.NguoiDungId
    after = _schedule_payload(db, schedule)
    notification_event_id = None
    if schedule_changed:
        recipient_ids = previous_recipients | {
            student.NguoiDungId
            for student in _attendance_roster(db, schedule)
        }
        recipient_ids.update(
            {previous_teacher_id, schedule.GiangVienId}
        )
        notification_event_id = queue_schedule_notifications(
            db,
            schedule_id=schedule.LichHocId,
            event_type="Thay đổi lịch",
            before=before_payload,
            after=after,
            reason=None,
            actor_id=current_user.NguoiDungId,
            occurred_at=schedule.NgayCapNhat,
            recipient_ids=recipient_ids,
        )
    db.add(
        LichHocLichSu(
            LichHocId=schedule.LichHocId,
            HanhDong="Cập nhật",
            DuLieuCu=before,
            DuLieuMoi=json.dumps(after, ensure_ascii=False),
            LyDo=request.ly_do_ghi_de,
            ThoiDiem=schedule.NgayCapNhat,
            NguoiThucHienId=current_user.NguoiDungId,
        )
    )
    _commit(db, "Không thể cập nhật lịch do dữ liệu bị trùng hoặc không hợp lệ.")
    _schedule_notification_delivery(
        notification_event_id,
        background_tasks,
        db,
    )
    return after


@router.put(
    "/schedules/{schedule_id}",
    dependencies=[Depends(require_permission("SCHEDULE_UPDATE"))],
)
def update_schedule_route(
    schedule_id: int,
    request: LichHocWrite,
    background_tasks: BackgroundTasks,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_schedule(
        schedule_id,
        request,
        current_user,
        db,
        background_tasks,
    )


def cancel_schedule(
    schedule_id: int,
    request: LichHocCancel,
    current_user: NguoiDung,
    db: Session,
    background_tasks: BackgroundTasks | None = None,
):
    _acquire_schedule_write_lock(db)
    schedule = _get_schedule_or_404(db, schedule_id)
    class_record = _get_class_or_404(db, schedule.LopHocId)
    if not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )
    if schedule.TrangThai != SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Buổi học không còn ở trạng thái có thể hủy.",
        )
    if datetime.combine(schedule.NgayHoc, schedule.GioBatDau) <= business_now_naive():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Buổi học đã bắt đầu hoặc đã diễn ra và không thể hủy.",
        )
    _ensure_no_attendance(db, schedule)

    before = _snapshot(db, schedule)
    before_payload = json.loads(before)
    recipient_ids = {
        student.NguoiDungId
        for student in _attendance_roster(db, schedule)
    }
    recipient_ids.add(schedule.GiangVienId)
    now = business_now_naive()
    schedule.TrangThai = CANCELLED
    schedule.LyDoHuy = request.ly_do
    schedule.NgayHuy = now
    schedule.NguoiHuyId = current_user.NguoiDungId
    schedule.NgayCapNhat = now
    schedule.NguoiCapNhatId = current_user.NguoiDungId
    after = _schedule_payload(db, schedule)
    notification_event_id = queue_schedule_notifications(
        db,
        schedule_id=schedule.LichHocId,
        event_type="Hủy buổi học",
        before=before_payload,
        after=after,
        reason=request.ly_do,
        actor_id=current_user.NguoiDungId,
        occurred_at=now,
        recipient_ids=recipient_ids,
    )
    db.add(
        LichHocLichSu(
            LichHocId=schedule.LichHocId,
            HanhDong="Hủy",
            DuLieuCu=before,
            DuLieuMoi=json.dumps(after, ensure_ascii=False),
            LyDo=request.ly_do,
            ThoiDiem=now,
            NguoiThucHienId=current_user.NguoiDungId,
        )
    )
    _commit(db, "Không thể hủy buổi học.")
    _schedule_notification_delivery(
        notification_event_id,
        background_tasks,
        db,
    )
    return after


@router.post(
    "/schedules/{schedule_id}/cancel",
    dependencies=[Depends(require_permission("SCHEDULE_UPDATE"))],
)
def cancel_schedule_route(
    schedule_id: int,
    request: LichHocCancel,
    background_tasks: BackgroundTasks,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return cancel_schedule(
        schedule_id,
        request,
        current_user,
        db,
        background_tasks,
    )


@router.post(
    "/schedule-notifications/retry",
    dependencies=[Depends(require_permission("SCHEDULE_UPDATE"))],
)
def retry_schedule_notifications(
    db: Session = Depends(get_db),
):
    return process_schedule_notifications(db, retry_failed=True)


def _attendance_payload(db: Session, schedule: LichHoc) -> dict:
    roster = _attendance_roster(db, schedule)
    student_ids = [student.NguoiDungId for student in roster]
    attendance_rows = (
        db.query(DiemDanh)
        .filter(
            DiemDanh.LichHocId == schedule.LichHocId,
            DiemDanh.HocVienId.in_(student_ids),
        )
        .all()
        if student_ids
        else []
    )
    legacy_attendance = (
        db.query(DiemDanhBuoiHoc)
        .filter(
            DiemDanhBuoiHoc.LichHocId == schedule.LichHocId,
            DiemDanhBuoiHoc.HocVienId.in_(student_ids),
        )
        .all()
        if student_ids
        else []
    )
    attendance_by_student = {item.HocVienId: item for item in attendance_rows}
    legacy_by_student = {item.HocVienId: item for item in legacy_attendance}
    actor_ids = {item.NguoiDiemDanhId for item in attendance_rows}
    actor_ids.update(item.NguoiCapNhatId for item in legacy_attendance)
    actors = (
        {
            user.NguoiDungId: user.HoTen
            for user in db.query(NguoiDung)
            .filter(NguoiDung.NguoiDungId.in_(actor_ids))
            .all()
        }
        if actor_ids
        else {}
    )
    return {
        "lichHocId": schedule.LichHocId,
        "maBuoiHoc": f"BH-{schedule.LichHocId:06d}",
        "ngayHoc": schedule.NgayHoc.isoformat(),
        "records": [
            {
                "hocVienId": student.NguoiDungId,
                "trangThai": (
                    attendance_by_student[student.NguoiDungId].TrangThai
                    if student.NguoiDungId in attendance_by_student
                    else (
                        legacy_by_student[student.NguoiDungId].TrangThai
                        if student.NguoiDungId in legacy_by_student
                        else None
                    )
                ),
            }
            for student in roster
        ],
        "hocViens": [
            {
                "hocVienId": student.NguoiDungId,
                "hoTen": student.HoTen,
                "email": student.Email,
                "trangThai": (
                    attendance_by_student[student.NguoiDungId].TrangThai
                    if student.NguoiDungId in attendance_by_student
                    else (
                        legacy_by_student[student.NguoiDungId].TrangThai
                        if student.NguoiDungId in legacy_by_student
                        else None
                    )
                ),
                "ghiChu": (
                    attendance_by_student[student.NguoiDungId].GhiChu
                    if student.NguoiDungId in attendance_by_student
                    else None
                ),
                "nguoiDiemDanh": (
                    actors.get(
                        attendance_by_student[student.NguoiDungId].NguoiDiemDanhId
                    )
                    if student.NguoiDungId in attendance_by_student
                    else (
                        actors.get(
                            legacy_by_student[student.NguoiDungId].NguoiCapNhatId
                        )
                        if student.NguoiDungId in legacy_by_student
                        else None
                    )
                ),
                "ngayCapNhat": (
                    attendance_by_student[student.NguoiDungId].NgayCapNhat.isoformat()
                    if student.NguoiDungId in attendance_by_student
                    else (
                        legacy_by_student[student.NguoiDungId].NgayCapNhat.isoformat()
                        if student.NguoiDungId in legacy_by_student
                        else None
                    )
                ),
            }
            for student in roster
        ],
        "trangThaiDiemDanh": _attendance_summary(db, schedule),
    }


def _ensure_attendance_scope(
    db: Session,
    schedule: LichHoc,
    current_user: NguoiDung,
) -> None:
    class_record = db.query(LopHoc).filter(
        LopHoc.LopHocId == schedule.LopHocId
    ).first()
    if class_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy lớp của buổi học.",
        )
    if not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )


@router.get(
    "/schedules/{schedule_id}/attendance",
    dependencies=[Depends(require_permission("ATTENDANCE_VIEW"))],
)
def get_schedule_attendance(
    schedule_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = _get_schedule_or_404(db, schedule_id)
    _ensure_attendance_scope(db, schedule, current_user)
    if STUDENT_ROLE_ID in user_role_ids(db, current_user.NguoiDungId):
        payload = _attendance_payload(db, schedule)
        payload["records"] = [
            record
            for record in payload["records"]
            if record["hocVienId"] == current_user.NguoiDungId
        ]
        payload["hocViens"] = [
            student
            for student in payload["hocViens"]
            if student["hocVienId"] == current_user.NguoiDungId
        ]
        return payload
    return _attendance_payload(db, schedule)


@router.put(
    "/schedules/{schedule_id}/attendance",
    dependencies=[Depends(require_permission("ATTENDANCE_UPDATE"))],
)
def update_schedule_attendance(
    schedule_id: int,
    request: DiemDanhWrite | DiemDanhBuoiHocWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _acquire_schedule_write_lock(db)
    schedule = _get_schedule_or_404(db, schedule_id)
    _ensure_attendance_scope(db, schedule, current_user)
    if isinstance(request, DiemDanhBuoiHocWrite):
        if schedule.TrangThai != SCHEDULED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Không thể điểm danh cho buổi học đã hủy.",
            )
        now = business_now_naive()
        start_at = datetime.combine(schedule.NgayHoc, schedule.GioBatDau)
        end_at = datetime.combine(schedule.NgayHoc, schedule.GioKetThuc)
        if now < start_at:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chỉ có thể điểm danh từ khi buổi học bắt đầu.",
            )
        role_ids = user_role_ids(db, current_user.NguoiDungId)
        is_training_manager = bool(role_ids.intersection({7, 8}))
        if now >= end_at and not is_training_manager:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Chỉ quản lý đào tạo được sửa điểm danh của buổi học đã kết thúc.",
            )
        if now >= end_at and not request.ly_do:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Cần nêu lý do khi điều chỉnh điểm danh của buổi học đã kết thúc.",
            )
        roster_ids = {
            student.NguoiDungId for student in _attendance_roster(db, schedule)
        }
        requested_ids = {entry.hoc_vien_id for entry in request.records}
        if not requested_ids.issubset(roster_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Danh sách có học viên không thuộc lớp tại ngày diễn ra buổi học.",
            )
        for entry in request.records:
            attendance = (
                db.query(DiemDanhBuoiHoc)
                .filter(
                    DiemDanhBuoiHoc.LichHocId == schedule.LichHocId,
                    DiemDanhBuoiHoc.HocVienId == entry.hoc_vien_id,
                )
                .first()
            )
            if entry.trang_thai is None:
                if attendance is not None:
                    if not request.ly_do:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Cần nhập lý do khi sửa điểm danh đã lưu.",
                        )
                    db.add(
                        DiemDanhBuoiHocLichSu(
                            LichHocId=schedule.LichHocId,
                            HocVienId=entry.hoc_vien_id,
                            TrangThaiCu=attendance.TrangThai,
                            TrangThaiMoi=None,
                            GhiChu=request.ly_do,
                            NguoiThucHienId=current_user.NguoiDungId,
                            ThoiDiem=now,
                        )
                    )
                    db.delete(attendance)
                continue
            if attendance is None:
                db.add(
                    DiemDanhBuoiHoc(
                        LichHocId=schedule.LichHocId,
                        HocVienId=entry.hoc_vien_id,
                        TrangThai=entry.trang_thai,
                        NgayCapNhat=now,
                        NguoiCapNhatId=current_user.NguoiDungId,
                    )
                )
            else:
                changed = attendance.TrangThai != entry.trang_thai
                if changed and not request.ly_do:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Cần nhập lý do khi sửa điểm danh đã lưu.",
                    )
                if changed:
                    db.add(
                        DiemDanhBuoiHocLichSu(
                            LichHocId=schedule.LichHocId,
                            HocVienId=entry.hoc_vien_id,
                            TrangThaiCu=attendance.TrangThai,
                            TrangThaiMoi=entry.trang_thai,
                            GhiChu=request.ly_do,
                            NguoiThucHienId=current_user.NguoiDungId,
                            ThoiDiem=now,
                        )
                    )
                attendance.TrangThai = entry.trang_thai
                attendance.NgayCapNhat = now
                attendance.NguoiCapNhatId = current_user.NguoiDungId
        _commit(
            db,
            "Không thể lưu điểm danh do dữ liệu bị trùng hoặc thay đổi đồng thời.",
        )
        return _attendance_payload(db, schedule)

    if schedule.TrangThai != SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể điểm danh cho buổi học đã hủy.",
        )
    now = business_now_naive()
    start_at = datetime.combine(schedule.NgayHoc, schedule.GioBatDau)
    end_at = datetime.combine(schedule.NgayHoc, schedule.GioKetThuc)
    if now < start_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chỉ có thể điểm danh từ khi buổi học bắt đầu.",
        )
    role_ids = user_role_ids(db, current_user.NguoiDungId)
    is_training_manager = bool(role_ids.intersection({7, 8}))
    if now >= end_at and not is_training_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ quản lý đào tạo được sửa điểm danh của buổi học đã kết thúc.",
        )
    if now >= end_at and not request.ly_do:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cần nêu lý do khi điều chỉnh điểm danh của buổi học đã kết thúc.",
        )

    roster_ids = {
        student.NguoiDungId for student in _attendance_roster(db, schedule)
    }
    requested_ids = {entry.hoc_vien_id for entry in request.hoc_viens}
    invalid_ids = requested_ids - roster_ids
    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Danh sách có học viên không thuộc lớp tại ngày diễn ra buổi học.",
        )

    existing_rows = (
        db.query(DiemDanh)
        .filter(
            DiemDanh.LichHocId == schedule.LichHocId,
            DiemDanh.HocVienId.in_(requested_ids),
        )
        .all()
    )
    existing_by_student = {item.HocVienId: item for item in existing_rows}
    for entry in request.hoc_viens:
        attendance = existing_by_student.get(entry.hoc_vien_id)
        old_status = attendance.TrangThai if attendance is not None else None
        old_note = attendance.GhiChu if attendance is not None else None
        if old_status == entry.trang_thai and old_note == entry.ghi_chu:
            continue
        if attendance is None:
            attendance = DiemDanh(
                LichHocId=schedule.LichHocId,
                HocVienId=entry.hoc_vien_id,
                NguoiDiemDanhId=current_user.NguoiDungId,
                NgayCapNhat=now,
            )
            db.add(attendance)
        attendance.TrangThai = entry.trang_thai
        attendance.GhiChu = entry.ghi_chu
        attendance.NguoiDiemDanhId = current_user.NguoiDungId
        attendance.NgayCapNhat = now
        db.add(
            AttendanceAudit(
                LichHocId=schedule.LichHocId,
                HocVienId=entry.hoc_vien_id,
                TrangThaiCu=old_status,
                TrangThaiMoi=entry.trang_thai,
                GhiChu=(
                    request.ly_do
                    or entry.ghi_chu
                ),
                NguoiThucHienId=current_user.NguoiDungId,
                ThoiDiem=now,
            )
        )

    _commit(db, "Không thể lưu điểm danh cho buổi học.")
    return _attendance_payload(db, schedule)


@router.get(
    "/schedules/{schedule_id}/attendance/audit",
    dependencies=[Depends(require_permission("SCHEDULE_VIEW"))],
)
def list_schedule_attendance_audit(
    schedule_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule = _get_schedule_or_404(db, schedule_id)
    _ensure_attendance_scope(db, schedule, current_user)
    cutoff = business_now_naive() - timedelta(days=360)
    roles = user_role_ids(db, current_user.NguoiDungId)
    student_id = (
        current_user.NguoiDungId
        if STUDENT_ROLE_ID in roles and not roles.intersection({7, 8})
        else None
    )
    query = (
        db.query(DiemDanhBuoiHocLichSu, NguoiDung.HoTen)
        .join(
            NguoiDung,
            NguoiDung.NguoiDungId == DiemDanhBuoiHocLichSu.NguoiThucHienId,
        )
        .filter(
            DiemDanhBuoiHocLichSu.LichHocId == schedule_id,
            DiemDanhBuoiHocLichSu.ThoiDiem >= cutoff,
        )
    )
    if student_id is not None:
        query = query.filter(DiemDanhBuoiHocLichSu.HocVienId == student_id)
    rows = query.order_by(
        DiemDanhBuoiHocLichSu.ThoiDiem.desc(),
        DiemDanhBuoiHocLichSu.LichSuId.desc(),
    ).all()
    return [
        {
            "id": item.LichSuId,
            "hocVienId": item.HocVienId,
            "trangThaiCu": item.TrangThaiCu,
            "trangThaiMoi": item.TrangThaiMoi,
            "lyDo": item.GhiChu,
            "nguoiThucHien": actor_name,
            "thoiDiem": item.ThoiDiem.isoformat(),
        }
        for item, actor_name in rows
    ]


def save_schedule_attendance(
    schedule_id: int,
    request: DiemDanhBuoiHocWrite,
    current_user: NguoiDung,
    db: Session,
):
    return update_schedule_attendance(
        schedule_id,
        request,
        current_user,
        db,
    )


def _history_payload(db: Session, item: LichHocLichSu) -> dict:
    schedule = _get_schedule_or_404(db, item.LichHocId)
    class_record = (
        db.query(LopHoc).filter(LopHoc.LopHocId == schedule.LopHocId).first()
    )
    actor = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == item.NguoiThucHienId)
        .first()
    )
    notification_query = db.query(LichHocThongBao).filter(
        LichHocThongBao.LichHocId == item.LichHocId,
        LichHocThongBao.ThoiDiemPhatSinh == item.ThoiDiem,
    )
    notification = notification_query.order_by(
        LichHocThongBao.LichHocThongBaoId
    ).first()
    notification_status = None
    if notification is not None:
        counts = dict(
            notification_query.with_entities(
                LichHocThongBao.TrangThai,
                func.count(LichHocThongBao.LichHocThongBaoId),
            )
            .group_by(LichHocThongBao.TrangThai)
            .all()
        )
        notification_status = {
            "total": sum(counts.values()),
            "sent": counts.get("Đã gửi", 0),
            "failed": counts.get("Thất bại", 0),
            "pending": counts.get("Chờ gửi", 0) + counts.get("Đang gửi", 0),
        }
    return {
        "lichHocLichSuId": item.LichHocLichSuId,
        "lichHocId": item.LichHocId,
        "maBuoiHoc": f"BH-{item.LichHocId:06d}",
        "maLop": class_record.MaLop if class_record else None,
        "tenLop": class_record.TenLop if class_record else None,
        "hanhDong": item.HanhDong,
        "duLieuCu": json.loads(item.DuLieuCu) if item.DuLieuCu else None,
        "duLieuMoi": json.loads(item.DuLieuMoi) if item.DuLieuMoi else None,
        "lyDo": item.LyDo,
        "thoiDiem": item.ThoiDiem.isoformat(),
        "nguoiThucHien": actor.HoTen if actor else None,
        "noiDungThongBao": notification.NoiDung if notification else None,
        "trangThaiThongBao": notification_status,
    }


def _history_json_value(db: Session, column, path: str):
    if db.get_bind().dialect.name == "mssql":
        return func.json_value(column, path)
    return func.json_extract(column, path)


@router.get(
    "/schedule-notifications",
)
def list_schedule_notifications(
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notifications = (
        db.query(LichHocThongBao)
        .filter(LichHocThongBao.NguoiNhanId == current_user.NguoiDungId)
        .order_by(LichHocThongBao.ThoiDiemPhatSinh.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": item.LichHocThongBaoId,
            "title": (
                "Buổi học đã bị hủy"
                if item.LoaiSuKien == "Hủy buổi học"
                else "Lịch học đã thay đổi"
            ),
            "message": item.NoiDung,
            "at": item.ThoiDiemPhatSinh.isoformat(),
        }
        for item in notifications
    ]


@router.get(
    "/schedule-history",
    dependencies=[Depends(require_permission("SCHEDULE_VIEW"))],
)
def list_schedule_history(
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(alias="q", max_length=200)] = None,
    event_type: Annotated[
        Literal["all", "date_time", "room", "instructor", "cancelled"],
        Query(alias="eventType"),
    ] = "all",
):
    class_ids = {
        item.LopHocId
        for item in accessible_classes(db, current_user, True)
    }
    if not class_ids:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "pageSize": page_size,
        }

    query = (
        db.query(LichHocLichSu)
        .join(LichHoc, LichHoc.LichHocId == LichHocLichSu.LichHocId)
        .join(LopHoc, LopHoc.LopHocId == LichHoc.LopHocId)
        .outerjoin(NguoiDung, NguoiDung.NguoiDungId == LichHocLichSu.NguoiThucHienId)
        .filter(LichHoc.LopHocId.in_(class_ids))
    )
    if event_type == "cancelled":
        query = query.filter(LichHocLichSu.HanhDong == "Hủy")
    elif event_type != "all":
        old_path, new_path = {
            "date_time": ("$.ngayHoc", "$.ngayHoc"),
            "room": ("$.phongHocId", "$.phongHocId"),
            "instructor": ("$.giangVienId", "$.giangVienId"),
        }[event_type]
        changed_fields = [
            (
                func.coalesce(
                    _history_json_value(db, LichHocLichSu.DuLieuCu, old_path),
                    "",
                )
                != func.coalesce(
                    _history_json_value(db, LichHocLichSu.DuLieuMoi, new_path),
                    "",
                )
            )
        ]
        if event_type == "date_time":
            for path in ("$.gioBatDau", "$.gioKetThuc"):
                changed_fields.append(
                    func.coalesce(
                        _history_json_value(db, LichHocLichSu.DuLieuCu, path),
                        "",
                    )
                    != func.coalesce(
                        _history_json_value(db, LichHocLichSu.DuLieuMoi, path),
                        "",
                    )
                )
        query = query.filter(
            LichHocLichSu.HanhDong == "Cập nhật",
            or_(*changed_fields),
        )

    term = (search or "").strip()
    if term:
        pattern = f"%{term.lower()}%"
        searchable = [
            func.lower(LopHoc.MaLop).like(pattern),
            func.lower(LopHoc.TenLop).like(pattern),
            func.lower(LichHocLichSu.HanhDong).like(pattern),
            func.lower(NguoiDung.HoTen).like(pattern),
            func.lower(func.coalesce(LichHocLichSu.LyDo, "")).like(pattern),
            func.lower(func.coalesce(LichHocLichSu.DuLieuCu, "")).like(pattern),
            func.lower(func.coalesce(LichHocLichSu.DuLieuMoi, "")).like(pattern),
        ]
        schedule_code = re.fullmatch(r"BH-(\d+)", term, flags=re.IGNORECASE)
        numeric_id = (
            int(schedule_code.group(1))
            if schedule_code
            else int(term)
            if term.isdecimal()
            else None
        )
        if numeric_id is not None:
            searchable.append(LichHoc.LichHocId == numeric_id)
        notice_match = (
            select(LichHocThongBao.LichHocThongBaoId)
            .where(
                LichHocThongBao.LichHocId == LichHoc.LichHocId,
                LichHocThongBao.ThoiDiemPhatSinh == LichHocLichSu.ThoiDiem,
                func.lower(LichHocThongBao.NoiDung).like(pattern),
            )
            .exists()
        )
        searchable.append(notice_match)
        query = query.filter(or_(*searchable))

    total = query.count()
    history = (
        query.order_by(
            LichHocLichSu.ThoiDiem.desc(),
            LichHocLichSu.LichHocLichSuId.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_history_payload(db, item) for item in history],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }
