import json
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, and_, cast, false, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.lich_hoc import LichHoc, LichHocLichSu
from app.models.lich_hoc_thong_bao import LichHocThongBao
from app.models.diem_danh import DiemDanh
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.student_enrollment_action import StudentEnrollmentAction
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.phong_hoc import PhongHoc
from app.schemas.lich_hoc import (
    DiemDanhWrite,
    LichHocCancel,
    LichHocWrite,
)
from app.services.academic_service import (
    TRAINING_MANAGER_ROLE_ID,
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
from app.services.business_time import business_now


router = APIRouter(prefix="/academic", tags=["Schedule management"])
SCHEDULED = "Đã lên lịch"
CANCELLED = "Đã hủy"


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
    recorded_count = (
        db.query(DiemDanh.DiemDanhId)
        .filter(
            DiemDanh.LichHocId == schedule.LichHocId,
            DiemDanh.HocVienId.in_([student.NguoiDungId for student in roster]),
        )
        .count()
    )
    if recorded_count == 0:
        return "Chưa điểm danh"
    return f"{recorded_count}/{len(roster)} đã điểm danh"


def _schedule_payload(db: Session, schedule: LichHoc) -> dict:
    class_record = (
        db.query(LopHoc).filter(LopHoc.LopHocId == schedule.LopHocId).first()
    )
    subject = db.query(MonHoc).filter(MonHoc.MonHocId == schedule.MonHocId).first()
    teacher = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == schedule.GiangVienId)
        .first()
    )
    room = (
        db.query(PhongHoc)
        .filter(PhongHoc.PhongHocId == schedule.PhongHocId)
        .first()
        if schedule.PhongHocId is not None
        else None
    )
    now = business_now()
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
) -> bool:
    is_training_manager = (
        TRAINING_MANAGER_ROLE_ID in user_role_ids(db, current_user.NguoiDungId)
    )
    if request.xac_nhan_trung_lich and not is_training_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ quản lý đào tạo được xác nhận ghi đè lịch bị trùng.",
        )
    if conflicts and not request.xac_nhan_trung_lich:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Lịch học bị trùng với buổi học đã được xếp.",
                "conflicts": conflicts,
                "canOverride": is_training_manager,
            },
        )
    return bool(conflicts and request.xac_nhan_trung_lich)


def _ensure_schedule_writable(schedule: LichHoc) -> None:
    if schedule.TrangThai != SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chỉ có thể chỉnh sửa buổi học đang ở trạng thái đã lên lịch.",
        )
    if datetime.combine(schedule.NgayHoc, schedule.GioBatDau) <= business_now():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Buổi học đã bắt đầu hoặc đã diễn ra và không thể chỉnh sửa lịch.",
        )


def _ensure_no_attendance(db: Session, schedule: LichHoc) -> None:
    has_attendance = (
        db.query(DiemDanh.DiemDanhId)
        .filter(DiemDanh.LichHocId == schedule.LichHocId)
        .first()
    )
    if has_attendance is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể thay đổi buổi học đã có dữ liệu điểm danh.",
        )


@router.get(
    "/schedule-options",
    dependencies=[Depends(require_permission("SCHEDULE_VIEW"))],
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
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ngày bắt đầu lọc không được sau ngày kết thúc.",
        )
    class_ids = {item.LopHocId for item in accessible_classes(db, current_user)}
    if not class_ids:
        return []

    query = db.query(LichHoc).filter(LichHoc.LopHocId.in_(class_ids))
    if start_date:
        query = query.filter(LichHoc.NgayHoc >= start_date)
    if end_date:
        query = query.filter(LichHoc.NgayHoc <= end_date)
    if status_filter == CANCELLED:
        query = query.filter(LichHoc.TrangThai == CANCELLED)
    elif status_filter == SCHEDULED:
        now = business_now()
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
        now = business_now()
        query = query.filter(
            LichHoc.TrangThai == SCHEDULED,
            LichHoc.NgayHoc == now.date(),
            LichHoc.GioBatDau <= now.time(),
            LichHoc.GioKetThuc > now.time(),
        )
    elif status_filter == "Đã diễn ra":
        now = business_now()
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
        _ensure_schedule_writable(schedule)
        if (
            request.lop_hoc_id != schedule.LopHocId
            or request.mon_hoc_id != schedule.MonHocId
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Không được thay đổi lớp hoặc môn học của buổi học.",
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
    conflicts = _find_conflicts(
        db,
        request,
        exclude_schedule_id=exclude_schedule_id,
    )
    is_training_manager = (
        TRAINING_MANAGER_ROLE_ID in user_role_ids(db, current_user.NguoiDungId)
    )
    return {
        "hasConflicts": bool(conflicts),
        "conflicts": conflicts,
        "canOverride": is_training_manager,
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
    try:
        ensure_active_instructor(db, request.giang_vien_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    _validate_room(db, request.phong_hoc_id)
    conflicts = _find_conflicts(db, request)
    conflict_override = _ensure_not_conflicting(
        conflicts, request, current_user, db
    )

    now = business_now()
    schedule = LichHoc(
        LopHocId=request.lop_hoc_id,
        MonHocId=request.mon_hoc_id,
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
    history_payload = payload
    if conflict_override:
        history_payload = {
            **payload,
            "xacNhanTrungLich": True,
            "lyDoGhiDe": request.ly_do_ghi_de,
            "xungDot": conflicts,
        }
    db.add(
        LichHocLichSu(
            LichHocId=schedule.LichHocId,
            HanhDong="Tạo",
            DuLieuMoi=json.dumps(history_payload, ensure_ascii=False),
            LyDo=request.ly_do_ghi_de if conflict_override else None,
            ThoiDiem=now,
            NguoiThucHienId=current_user.NguoiDungId,
        )
    )
    _commit(db, "Không thể tạo buổi học do dữ liệu bị trùng hoặc không hợp lệ.")
    if conflict_override:
        return {
            **payload,
            "ghiDe": {
                "xacNhan": True,
                "lyDo": request.ly_do_ghi_de,
                "soXungDot": len(conflicts),
            },
        }
    return payload


@router.put(
    "/schedules/{schedule_id}",
    dependencies=[Depends(require_permission("SCHEDULE_UPDATE"))],
)
def update_schedule(
    schedule_id: int,
    request: LichHocWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _acquire_schedule_write_lock(db)
    schedule = _get_schedule_or_404(db, schedule_id)
    class_record = _get_class_or_404(db, schedule.LopHocId)
    if not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )
    _ensure_schedule_writable(schedule)
    _ensure_no_attendance(db, schedule)
    if request.lop_hoc_id != schedule.LopHocId or request.mon_hoc_id != schedule.MonHocId:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Không được thay đổi lớp hoặc môn học của buổi học.",
        )
    _validate_class_subject(db, class_record, schedule.MonHocId)
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
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Lịch học bị trùng với buổi học đã được xếp.",
                "conflicts": conflicts,
                "canOverride": False,
            },
        )

    previous_teacher_id = schedule.GiangVienId
    previous_values = (
        schedule.NgayHoc,
        schedule.GioBatDau,
        schedule.GioKetThuc,
        schedule.PhongHocId,
        schedule.GiangVienId,
    )
    updated_values = (
        request.ngay_hoc,
        request.gio_bat_dau,
        request.gio_ket_thuc,
        request.phong_hoc_id,
        request.giang_vien_id,
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
    schedule.GioBatDau = request.gio_bat_dau
    schedule.GioKetThuc = request.gio_ket_thuc
    schedule.PhongHocId = request.phong_hoc_id
    schedule.GiangVienId = request.giang_vien_id
    schedule.NgayCapNhat = business_now()
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
            LyDo=None,
            ThoiDiem=schedule.NgayCapNhat,
            NguoiThucHienId=current_user.NguoiDungId,
        )
    )
    _commit(db, "Không thể cập nhật lịch do dữ liệu bị trùng hoặc không hợp lệ.")
    notification_result = None
    if notification_event_id is not None:
        notification_result = process_schedule_notifications(
            db,
            event_id=notification_event_id,
        )
    return {
        **after,
        "trangThaiGuiThongBao": notification_result,
    }


@router.post(
    "/schedules/{schedule_id}/cancel",
    dependencies=[Depends(require_permission("SCHEDULE_UPDATE"))],
)
def cancel_schedule(
    schedule_id: int,
    request: LichHocCancel,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
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
    if datetime.combine(schedule.NgayHoc, schedule.GioBatDau) <= business_now():
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
    now = business_now()
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
    notification_result = None
    if notification_event_id is not None:
        notification_result = process_schedule_notifications(
            db,
            event_id=notification_event_id,
        )
    return {
        **after,
        "trangThaiGuiThongBao": notification_result,
    }


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
    attendance_by_student = {item.HocVienId: item for item in attendance_rows}
    actor_ids = {item.NguoiDiemDanhId for item in attendance_rows}
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
        "hocViens": [
            {
                "hocVienId": student.NguoiDungId,
                "hoTen": student.HoTen,
                "email": student.Email,
                "trangThai": (
                    attendance_by_student[student.NguoiDungId].TrangThai
                    if student.NguoiDungId in attendance_by_student
                    else None
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
                    else None
                ),
                "ngayCapNhat": (
                    attendance_by_student[student.NguoiDungId].NgayCapNhat.isoformat()
                    if student.NguoiDungId in attendance_by_student
                    else None
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
    return _attendance_payload(db, schedule)


@router.put(
    "/schedules/{schedule_id}/attendance",
    dependencies=[Depends(require_permission("ATTENDANCE_UPDATE"))],
)
def update_schedule_attendance(
    schedule_id: int,
    request: DiemDanhWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _acquire_schedule_write_lock(db)
    schedule = _get_schedule_or_404(db, schedule_id)
    _ensure_attendance_scope(db, schedule, current_user)
    if schedule.TrangThai != SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể điểm danh cho buổi học đã hủy.",
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
    now = business_now()
    for entry in request.hoc_viens:
        attendance = existing_by_student.get(entry.hoc_vien_id)
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

    _commit(db, "Không thể lưu điểm danh cho buổi học.")
    return _attendance_payload(db, schedule)


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
    notifications = (
        db.query(LichHocThongBao.TrangThai, LichHocThongBao.NoiDung)
        .filter(
            LichHocThongBao.LichHocId == item.LichHocId,
            LichHocThongBao.NguoiThucHienId == item.NguoiThucHienId,
            LichHocThongBao.ThoiDiemPhatSinh == item.ThoiDiem,
        )
        .all()
    )
    notification_statuses = [status for status, _ in notifications]
    notification_summary = None
    if notification_statuses:
        sent = notification_statuses.count("Đã gửi")
        failed = notification_statuses.count("Thất bại")
        pending = len(notification_statuses) - sent - failed
        notification_summary = {
            "total": len(notification_statuses),
            "sent": sent,
            "failed": failed,
            "pending": pending,
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
        "noiDungThongBao": notifications[0][1] if notifications else None,
        "trangThaiThongBao": notification_summary,
    }


@router.get(
    "/schedule-history",
    dependencies=[Depends(require_permission("SCHEDULE_VIEW"))],
)
def list_schedule_history(
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
    query_text: Annotated[str | None, Query(max_length=200, alias="q")] = None,
    event_type: Annotated[str, Query(alias="eventType")] = "all",
):
    class_ids = [
        item.LopHocId for item in accessible_classes(db, current_user, True)
    ]
    if not class_ids:
        return {"items": [], "total": 0, "page": page, "pageSize": page_size}

    query = (
        db.query(LichHocLichSu)
        .join(LichHoc, LichHoc.LichHocId == LichHocLichSu.LichHocId)
        .join(LopHoc, LopHoc.LopHocId == LichHoc.LopHocId)
        .outerjoin(
            NguoiDung,
            NguoiDung.NguoiDungId == LichHocLichSu.NguoiThucHienId,
        )
        .filter(LichHoc.LopHocId.in_(class_ids))
    )

    dialect = db.get_bind().dialect.name

    def json_value(column, path: str):
        if dialect == "mssql":
            return func.json_value(column, path)
        return func.json_extract(column, path)

    old_date = func.coalesce(
        json_value(LichHocLichSu.DuLieuCu, "$.ngayHoc"), ""
    )
    new_date = func.coalesce(
        json_value(LichHocLichSu.DuLieuMoi, "$.ngayHoc"), ""
    )
    old_start = func.coalesce(
        json_value(LichHocLichSu.DuLieuCu, "$.gioBatDau"), ""
    )
    new_start = func.coalesce(
        json_value(LichHocLichSu.DuLieuMoi, "$.gioBatDau"), ""
    )
    old_end = func.coalesce(
        json_value(LichHocLichSu.DuLieuCu, "$.gioKetThuc"), ""
    )
    new_end = func.coalesce(
        json_value(LichHocLichSu.DuLieuMoi, "$.gioKetThuc"), ""
    )
    old_room = func.coalesce(
        json_value(LichHocLichSu.DuLieuCu, "$.phongHocId"), ""
    )
    new_room = func.coalesce(
        json_value(LichHocLichSu.DuLieuMoi, "$.phongHocId"), ""
    )
    old_teacher = func.coalesce(
        json_value(LichHocLichSu.DuLieuCu, "$.giangVienId"), ""
    )
    new_teacher = func.coalesce(
        json_value(LichHocLichSu.DuLieuMoi, "$.giangVienId"), ""
    )

    if event_type == "date_time":
        query = query.filter(
            LichHocLichSu.HanhDong == "Cập nhật",
            or_(old_date != new_date, old_start != new_start, old_end != new_end),
        )
    elif event_type == "room":
        query = query.filter(
            LichHocLichSu.HanhDong == "Cập nhật",
            old_room != new_room,
        )
    elif event_type == "instructor":
        query = query.filter(
            LichHocLichSu.HanhDong == "Cập nhật",
            old_teacher != new_teacher,
        )
    elif event_type == "cancelled":
        query = query.filter(LichHocLichSu.HanhDong == "Hủy")
    elif event_type != "all":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Loại sự kiện không hợp lệ.",
        )

    normalized_query = (query_text or "").strip()
    if normalized_query:
        search_term = normalized_query
        pattern = f"%{search_term}%"
        if search_term.casefold().startswith("bh-"):
            schedule_number = search_term[3:]
            if schedule_number.isdigit() and len(schedule_number) <= 10:
                schedule_id = int(schedule_number)
                schedule_code_term = (
                    LichHoc.LichHocId == schedule_id
                    if schedule_id <= 2_147_483_647
                    else false()
                )
            else:
                schedule_code_term = false()
        else:
            schedule_code_term = cast(LichHoc.LichHocId, String).ilike(pattern)
        notification_match = (
            select(LichHocThongBao.LichHocThongBaoId)
            .where(
                LichHocThongBao.LichHocId == LichHoc.LichHocId,
                LichHocThongBao.NguoiThucHienId
                == LichHocLichSu.NguoiThucHienId,
                LichHocThongBao.ThoiDiemPhatSinh == LichHocLichSu.ThoiDiem,
                LichHocThongBao.NoiDung.ilike(pattern),
            )
            .exists()
        )
        query = query.filter(
            or_(
                schedule_code_term,
                LopHoc.MaLop.ilike(pattern),
                LopHoc.TenLop.ilike(pattern),
                NguoiDung.HoTen.ilike(pattern),
                LichHocLichSu.HanhDong.ilike(pattern),
                LichHocLichSu.LyDo.ilike(pattern),
                LichHocLichSu.DuLieuCu.ilike(pattern),
                LichHocLichSu.DuLieuMoi.ilike(pattern),
                notification_match,
            )
        )

    total = query.order_by(None).count()
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
