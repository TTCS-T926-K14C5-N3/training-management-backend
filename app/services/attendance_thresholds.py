from collections.abc import Iterable
import logging

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.attendance import (
    AbsenceThreshold,
    AttendanceNotification,
    AttendanceRecord,
)
from app.models.diem_danh_buoi_hoc import DiemDanhBuoiHoc
from app.models.lich_hoc import LichHoc
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro

MANAGER_ROLE_IDS = {7, 8}
UNEXCUSED_STATUSES = {"unexcused_absence", "Vắng không phép"}
logger = logging.getLogger(__name__)


def threshold_for_program(db: Session, program_id: int | None) -> int:
    if program_id is None:
        return 20
    threshold = (
        db.query(AbsenceThreshold)
        .filter(AbsenceThreshold.ChuongTrinhId == program_id)
        .first()
    )
    return threshold.TiLeToiDa if threshold else 20


def absence_metrics_by_student(
    db: Session,
    program_id: int,
    student_ids: Iterable[int] | None = None,
) -> dict[int, tuple[int, int, float]]:
    """Count recorded absences across both attendance workflows without double-counting a class day."""
    student_ids = set(student_ids) if student_ids is not None else None
    daily_query = (
        db.query(
            AttendanceRecord.HocVienId,
            AttendanceRecord.LopHocId,
            AttendanceRecord.NgayHoc,
            AttendanceRecord.TrangThai,
        )
        .join(LopHoc, LopHoc.LopHocId == AttendanceRecord.LopHocId)
        .filter(LopHoc.ChuongTrinhId == program_id)
    )
    session_query = (
        db.query(
            DiemDanhBuoiHoc.HocVienId,
            LichHoc.LopHocId,
            LichHoc.NgayHoc,
            DiemDanhBuoiHoc.TrangThai,
        )
        .join(LichHoc, LichHoc.LichHocId == DiemDanhBuoiHoc.LichHocId)
        .join(LopHoc, LopHoc.LopHocId == LichHoc.LopHocId)
        .filter(
            LopHoc.ChuongTrinhId == program_id,
            LichHoc.TrangThai != "Đã hủy",
        )
    )
    if student_ids is not None:
        if not student_ids:
            return {}
        daily_query = daily_query.filter(
            AttendanceRecord.HocVienId.in_(student_ids)
        )
        session_query = session_query.filter(
            DiemDanhBuoiHoc.HocVienId.in_(student_ids)
        )

    if inspect(db.get_bind()).has_table(AttendanceRecord.__tablename__):
        daily_rows = daily_query.all()
    else:
        logger.warning(
            "Table %s is missing; absence thresholds only include session attendance until migration 017 is applied.",
            AttendanceRecord.__tablename__,
        )
        daily_rows = []
    session_rows = session_query.all()
    session_days = {
        (student_id, class_id, session_date)
        for student_id, class_id, session_date, _ in session_rows
    }
    totals: dict[int, list[int]] = {}
    for student_id, class_id, session_date, state in daily_rows:
        if (student_id, class_id, session_date) in session_days:
            continue
        counts = totals.setdefault(student_id, [0, 0])
        counts[0] += int(state in UNEXCUSED_STATUSES)
        counts[1] += 1
    for student_id, _class_id, _session_date, state in session_rows:
        counts = totals.setdefault(student_id, [0, 0])
        counts[0] += int(state in UNEXCUSED_STATUSES)
        counts[1] += 1

    return {
        student_id: (
            values[0],
            values[1],
            values[0] * 100 / values[1] if values[1] else 0,
        )
        for student_id, values in totals.items()
    }


def absence_metrics_for_student(
    db: Session, student_id: int, program_id: int
) -> tuple[int, int, float]:
    return absence_metrics_by_student(db, program_id, [student_id]).get(
        student_id, (0, 0, 0.0)
    )


def notify_threshold_activation(
    db: Session,
    student_id: int,
    program_id: int,
    *,
    was_above_threshold: bool,
) -> bool:
    absent, total, rate = absence_metrics_for_student(db, student_id, program_id)
    threshold = threshold_for_program(db, program_id)
    if total == 0 or was_above_threshold or rate < threshold:
        return False

    student = db.query(NguoiDung).filter(
        NguoiDung.NguoiDungId == student_id
    ).first()
    if student is None:
        return False

    class_ids = {
        row[0]
        for row in db.query(LopHoc.LopHocId)
        .filter(LopHoc.ChuongTrinhId == program_id)
        .all()
    }
    teacher_ids = {
        row[0]
        for row in db.query(LopHoc.GiangVienId)
        .filter(
            LopHoc.ChuongTrinhId == program_id,
            LopHoc.GiangVienId.isnot(None),
        )
        .all()
    }
    if class_ids:
        teacher_ids.update(
            row[0]
            for row in db.query(LichHoc.GiangVienId)
            .filter(
                LichHoc.LopHocId.in_(class_ids),
                LichHoc.GiangVienId.isnot(None),
            )
            .distinct()
            .all()
        )
        teacher_ids.update(
            row[0]
            for row in db.query(LopHocMonHocGiangVien.GiangVienId)
            .filter(LopHocMonHocGiangVien.LopHocId.in_(class_ids))
            .distinct()
            .all()
        )
    manager_ids = {
        row[0]
        for row in db.query(NguoiDungVaiTro.NguoiDungId)
        .filter(NguoiDungVaiTro.VaiTroId.in_(MANAGER_ROLE_IDS))
        .distinct()
        .all()
    }
    recipients = teacher_ids | manager_ids | {student_id}
    for recipient_id in recipients:
        message = (
            f"Tỷ lệ vắng không phép của bạn là {rate:.1f}% ({absent}/{total}), "
            f"đạt ngưỡng cảnh báo {threshold}%."
            if recipient_id == student_id
            else (
                f"Học viên {student.HoTen} vắng không phép {absent}/{total} buổi "
                f"({rate:.1f}%), đạt ngưỡng cảnh báo {threshold}%."
            )
        )
        db.add(
            AttendanceNotification(
                NguoiNhanId=recipient_id,
                HocVienId=student_id,
                ChuongTrinhId=program_id,
                Loai="absence_threshold",
                TieuDe="Cảnh báo tỷ lệ vắng",
                NoiDung=message,
            )
        )
    return True
