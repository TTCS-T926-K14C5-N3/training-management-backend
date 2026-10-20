import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.lich_hoc import LichHoc, LichHocLichSu, LichHocThongBao
from app.models.diem_danh_buoi_hoc import DiemDanhBuoiHoc
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.mon_hoc import MonHoc
from app.models.program_subject import BuoiHoc, ChuongTrinhMonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.phong_hoc import PhongHoc
from app.schemas.lich_hoc import (
    DiemDanhBuoiHocWrite,
    LichHocCancel,
    LichHocGenerate,
    LichHocWrite,
)
from app.services.academic_service import (
    TEACHING_ROLE_IDS,
    accessible_classes,
    can_access_class,
    ensure_active_instructor,
    user_is_admin,
    user_role_ids,
)


router = APIRouter(prefix="/academic", tags=["Schedule management"])
SCHEDULED = "Đã lên lịch"
CANCELLED = "Đã hủy"
TRAINING_MANAGER_ROLE_ID = 7
ADMIN_ROLE_ID = 8


def _commit(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from error


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


def _schedule_payload(db: Session, schedule: LichHoc) -> dict:
    class_record = (
        db.query(LopHoc).filter(LopHoc.LopHocId == schedule.LopHocId).first()
    )
    subject = db.query(MonHoc).filter(MonHoc.MonHocId == schedule.MonHocId).first()
    lesson = (
        db.query(BuoiHoc).filter(BuoiHoc.BuoiHocId == schedule.BuoiHocId).first()
        if schedule.BuoiHocId is not None
        else None
    )
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
    now = datetime.now()
    student_count = (
        db.query(LopHocHocVien.HocVienId)
        .filter(LopHocHocVien.LopHocId == schedule.LopHocId)
        .count()
    )
    marked_count = (
        db.query(DiemDanhBuoiHoc.DiemDanhBuoiHocId)
        .filter(DiemDanhBuoiHoc.LichHocId == schedule.LichHocId)
        .count()
    )
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
        "soThuTuBuoi": lesson.SoThuTu if lesson else None,
        "chuDeBuoiHoc": lesson.ChuDe if lesson else None,
        "ngayHoc": schedule.NgayHoc.isoformat(),
        "gioBatDau": schedule.GioBatDau.strftime("%H:%M"),
        "gioKetThuc": schedule.GioKetThuc.strftime("%H:%M"),
        "phongHocId": schedule.PhongHocId,
        "maPhong": room.MaPhong if room else None,
        "tenPhong": room.TenPhong if room else None,
        "giangVienId": schedule.GiangVienId,
        "giangVienTen": teacher.HoTen if teacher else None,
        "trangThai": state,
        "coTheChinhSua": state == SCHEDULED and marked_count == 0,
        "coTheHuy": state == SCHEDULED and marked_count == 0,
        "trangThaiDiemDanh": (
            f"Đã ghi nhận {marked_count}/{student_count}"
            if marked_count
            else "Chưa điểm danh"
        ),
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


def _schedule_summary(payload: dict) -> str:
    room = "Chưa gán phòng"
    if payload.get("maPhong"):
        room = f"{payload['maPhong']} · {payload.get('tenPhong') or ''}".strip()
    teacher = payload.get("giangVienTen") or "Chưa có giảng viên"
    return (
        f"{payload.get('ngayHoc')} · {payload.get('gioBatDau')}–"
        f"{payload.get('gioKetThuc')}; {room}; giảng viên: {teacher}"
    )


def _notify_schedule_change(
    db: Session,
    schedule: LichHoc,
    class_record: LopHoc,
    action: str,
    before: dict,
    after: dict,
    changed_at: datetime,
    reason: str | None = None,
) -> None:
    recipient_ids = {
        student_id
        for (student_id,) in db.query(LopHocHocVien.HocVienId)
        .filter(LopHocHocVien.LopHocId == class_record.LopHocId)
        .all()
    }
    recipient_ids.update(
        user_id
        for user_id in (
            before.get("giangVienId"),
            after.get("giangVienId"),
            class_record.GiangVienId,
        )
        if user_id is not None
    )
    if action == "Hủy":
        title = "Buổi học đã bị hủy"
        message = (
            f"Buổi {after['maBuoiHoc']} của lớp {after.get('maLop') or ''} "
            f"ngày {after['ngayHoc']} đã bị hủy. Lý do: {reason}"
        )
    else:
        title = "Lịch học đã thay đổi"
        message = (
            f"Buổi {after['maBuoiHoc']} của lớp {after.get('maLop') or ''} "
            f"đã thay đổi. Lịch mới: {_schedule_summary(after)}."
        )

    db.add_all(
        LichHocThongBao(
            LichHocId=schedule.LichHocId,
            NguoiNhanId=recipient_id,
            TieuDe=title,
            NoiDung=message,
            ThoiDiem=changed_at,
        )
        for recipient_id in recipient_ids
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


def _validate_lesson(
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
            detail="Bài học không thuộc môn học và chương trình của lớp.",
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
            detail="Bài học này đã được xếp lịch cho lớp.",
        )


def _validate_room(db: Session, room_id: int | None) -> None:
    if room_id is None:
        return
    room = db.query(PhongHoc).filter(PhongHoc.PhongHocId == room_id).first()
    if room is None or room.TrangThai != "Đang hoạt động":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Phòng học không tồn tại hoặc đã ngừng hoạt động.",
        )


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
    for existing in overlaps:
        labels = []
        class_record = (
            db.query(LopHoc)
            .filter(LopHoc.LopHocId == existing.LopHocId)
            .first()
        )
        if existing.LopHocId == request.lop_hoc_id:
            labels.append(
                {
                    "loai": "lopHoc",
                    "ten": class_record.TenLop if class_record else None,
                }
            )
        if existing.GiangVienId == request.giang_vien_id:
            teacher = (
                db.query(NguoiDung)
                .filter(NguoiDung.NguoiDungId == request.giang_vien_id)
                .first()
            )
            labels.append(
                {
                    "loai": "giangVien",
                    "ten": teacher.HoTen if teacher else None,
                }
            )
        if (
            request.phong_hoc_id is not None
            and existing.PhongHocId == request.phong_hoc_id
        ):
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


def _ensure_not_conflicting(conflicts: list[dict]) -> None:
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Lịch học bị trùng với buổi học đã được xếp.",
                "conflicts": conflicts,
            },
        )


def _ensure_schedule_writable(db: Session, schedule: LichHoc) -> None:
    has_attendance = (
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
    if datetime.combine(schedule.NgayHoc, schedule.GioBatDau) <= datetime.now():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Buổi học đã bắt đầu hoặc đã diễn ra và không thể chỉnh sửa lịch.",
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
                        "buoiHocs": [
                            {
                                "buoiHocId": lesson.BuoiHocId,
                                "soThuTu": lesson.SoThuTu,
                                "chuDe": lesson.ChuDe,
                            }
                            for lesson in _get_subject_lessons(
                                db, class_record, subject.MonHocId
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


def _get_schedule_class(
    db: Session,
    schedule_id: int,
    current_user: NguoiDung,
) -> tuple[LichHoc, LopHoc]:
    schedule = _get_schedule_or_404(db, schedule_id)
    class_record = db.query(LopHoc).filter(
        LopHoc.LopHocId == schedule.LopHocId
    ).first()
    if class_record is None or not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem điểm danh của lớp này.",
        )
    return schedule, class_record


def _attendance_records(
    db: Session,
    schedule: LichHoc,
    class_record: LopHoc,
    student_id: int | None = None,
) -> list[dict]:
    query = (
        db.query(NguoiDung, DiemDanhBuoiHoc.TrangThai)
        .join(
            LopHocHocVien,
            LopHocHocVien.HocVienId == NguoiDung.NguoiDungId,
        )
        .outerjoin(
            DiemDanhBuoiHoc,
            and_(
                DiemDanhBuoiHoc.HocVienId == NguoiDung.NguoiDungId,
                DiemDanhBuoiHoc.LichHocId == schedule.LichHocId,
            ),
        )
        .filter(LopHocHocVien.LopHocId == class_record.LopHocId)
    )
    if student_id is not None:
        query = query.filter(NguoiDung.NguoiDungId == student_id)
    return [
        {
            "hocVienId": student.NguoiDungId,
            "hoTen": student.HoTen,
            "email": student.Email,
            "trangThai": attendance_status,
        }
        for student, attendance_status in query.order_by(NguoiDung.HoTen).all()
    ]


@router.get(
    "/schedules/{schedule_id}/attendance",
    dependencies=[Depends(require_permission("SCHEDULE_VIEW"))],
)
def get_schedule_attendance(
    schedule_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule, class_record = _get_schedule_class(db, schedule_id, current_user)
    student_roles = user_role_ids(db, current_user.NguoiDungId)
    student_id = (
        current_user.NguoiDungId
        if 2 in student_roles and not student_roles.intersection({7, 8})
        else None
    )
    records = _attendance_records(db, schedule, class_record, student_id)
    return {
        "lichHocId": schedule.LichHocId,
        "maBuoiHoc": f"BH-{schedule.LichHocId:06d}",
        "maLop": class_record.MaLop,
        "tenLop": class_record.TenLop,
        "ngayHoc": schedule.NgayHoc.isoformat(),
        "gioBatDau": schedule.GioBatDau.strftime("%H:%M"),
        "gioKetThuc": schedule.GioKetThuc.strftime("%H:%M"),
        "records": records,
        "coTheCapNhat": (
            not student_roles.intersection({2})
            and (
                user_is_admin(db, current_user.NguoiDungId)
                or bool(student_roles.intersection({TRAINING_MANAGER_ROLE_ID, *TEACHING_ROLE_IDS}))
            )
        ),
    }


@router.put(
    "/schedules/{schedule_id}/attendance",
    dependencies=[Depends(require_permission("SCHEDULE_UPDATE"))],
)
def save_schedule_attendance(
    schedule_id: int,
    request: DiemDanhBuoiHocWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    schedule, class_record = _get_schedule_class(db, schedule_id, current_user)
    roles = user_role_ids(db, current_user.NguoiDungId)
    if not (
        user_is_admin(db, current_user.NguoiDungId)
        or roles.intersection({TRAINING_MANAGER_ROLE_ID, *TEACHING_ROLE_IDS})
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ giảng viên hoặc quản lý đào tạo mới được cập nhật điểm danh.",
        )
    if schedule.TrangThai == CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể điểm danh buổi học đã bị hủy.",
        )

    enrolled_ids = {
        student_id
        for (student_id,) in db.query(LopHocHocVien.HocVienId)
        .filter(LopHocHocVien.LopHocId == class_record.LopHocId)
        .all()
    }
    requested_ids = {record.hoc_vien_id for record in request.records}
    if not requested_ids.issubset(enrolled_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Danh sách có học viên không thuộc lớp này.",
        )

    now = datetime.now()
    for record in request.records:
        existing = (
            db.query(DiemDanhBuoiHoc)
            .filter(
                DiemDanhBuoiHoc.LichHocId == schedule.LichHocId,
                DiemDanhBuoiHoc.HocVienId == record.hoc_vien_id,
            )
            .first()
        )
        if record.trang_thai is None:
            if existing is not None:
                db.delete(existing)
            continue
        if existing is None:
            db.add(
                DiemDanhBuoiHoc(
                    LichHocId=schedule.LichHocId,
                    HocVienId=record.hoc_vien_id,
                    TrangThai=record.trang_thai,
                    NgayCapNhat=now,
                    NguoiCapNhatId=current_user.NguoiDungId,
                )
            )
        else:
            existing.TrangThai = record.trang_thai
            existing.NgayCapNhat = now
            existing.NguoiCapNhatId = current_user.NguoiDungId
    _commit(db, "Không thể lưu điểm danh do dữ liệu bị trùng hoặc thay đổi đồng thời.")
    return get_schedule_attendance(schedule_id, current_user, db)


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
    _ensure_not_conflicting(conflicts)

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
        now = datetime.now()
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
        now = datetime.now()
        query = query.filter(
            LichHoc.TrangThai == SCHEDULED,
            LichHoc.NgayHoc == now.date(),
            LichHoc.GioBatDau <= now.time(),
            LichHoc.GioKetThuc > now.time(),
        )
    elif status_filter == "Đã diễn ra":
        now = datetime.now()
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
    "/schedules",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("SCHEDULE_CREATE"))],
)
def create_schedule(
    request: LichHocWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    class_record = _get_class_or_404(db, request.lop_hoc_id)
    if not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )
    _validate_class_subject(db, class_record, request.mon_hoc_id)
    _validate_lesson(db, class_record, request.mon_hoc_id, request.buoi_hoc_id)
    try:
        ensure_active_instructor(db, request.giang_vien_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    _validate_room(db, request.phong_hoc_id)
    _ensure_not_conflicting(_find_conflicts(db, request))

    now = datetime.now()
    schedule = LichHoc(
        LopHocId=request.lop_hoc_id,
        MonHocId=request.mon_hoc_id,
        BuoiHocId=request.buoi_hoc_id,
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
            ThoiDiem=now,
            NguoiThucHienId=current_user.NguoiDungId,
        )
    )
    _commit(db, "Không thể tạo buổi học do dữ liệu bị trùng hoặc không hợp lệ.")
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
    schedule = _get_schedule_or_404(db, schedule_id)
    class_record = _get_class_or_404(db, schedule.LopHocId)
    if not can_access_class(db, current_user, class_record):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )
    _ensure_schedule_writable(db, schedule)
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
    _ensure_not_conflicting(
        _find_conflicts(db, request, exclude_schedule_id=schedule_id)
    )

    before = _snapshot(db, schedule)
    schedule.NgayHoc = request.ngay_hoc
    schedule.BuoiHocId = request.buoi_hoc_id
    schedule.GioBatDau = request.gio_bat_dau
    schedule.GioKetThuc = request.gio_ket_thuc
    schedule.PhongHocId = request.phong_hoc_id
    schedule.GiangVienId = request.giang_vien_id
    schedule.NgayCapNhat = datetime.now()
    schedule.NguoiCapNhatId = current_user.NguoiDungId
    after = _schedule_payload(db, schedule)
    db.add(
        LichHocLichSu(
            LichHocId=schedule.LichHocId,
            HanhDong="Cập nhật",
            DuLieuCu=before,
            DuLieuMoi=json.dumps(after, ensure_ascii=False),
            ThoiDiem=schedule.NgayCapNhat,
            NguoiThucHienId=current_user.NguoiDungId,
        )
    )
    _notify_schedule_change(
        db,
        schedule,
        class_record,
        "Cập nhật",
        json.loads(before),
        after,
        schedule.NgayCapNhat,
    )
    _commit(db, "Không thể cập nhật lịch do dữ liệu bị trùng hoặc không hợp lệ.")
    return after


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
    if datetime.combine(schedule.NgayHoc, schedule.GioBatDau) <= datetime.now():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Buổi học đã bắt đầu hoặc đã diễn ra và không thể hủy.",
        )
    _ensure_schedule_writable(db, schedule)

    before = _snapshot(db, schedule)
    now = datetime.now()
    schedule.TrangThai = CANCELLED
    schedule.LyDoHuy = request.ly_do
    schedule.NgayHuy = now
    schedule.NguoiHuyId = current_user.NguoiDungId
    schedule.NgayCapNhat = now
    schedule.NguoiCapNhatId = current_user.NguoiDungId
    after = _schedule_payload(db, schedule)
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
    _notify_schedule_change(
        db,
        schedule,
        class_record,
        "Hủy",
        json.loads(before),
        after,
        now,
        request.ly_do,
    )
    _commit(db, "Không thể hủy buổi học.")
    return after


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
    }


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
        .order_by(LichHocThongBao.ThoiDiem.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": item.LichHocThongBaoId,
            "title": item.TieuDe,
            "message": item.NoiDung,
            "at": item.ThoiDiem.isoformat(),
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
):
    class_ids = {item.LopHocId for item in accessible_classes(db, current_user, True)}
    if not class_ids:
        return []
    schedule_ids = (
        select(LichHoc.LichHocId).where(LichHoc.LopHocId.in_(class_ids))
    )
    history = (
        db.query(LichHocLichSu)
        .filter(LichHocLichSu.LichHocId.in_(schedule_ids))
        .order_by(LichHocLichSu.ThoiDiem.desc())
        .limit(100)
        .all()
    )
    return [_history_payload(db, item) for item in history]
