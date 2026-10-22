from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.attendance import (
    AbsenceRequest,
    AbsenceThreshold,
    AttendanceAudit,
    AttendanceNotification,
    AttendanceRecord,
)
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.routers.attendance import (
    AbsenceDecision,
    AbsenceRequestInput,
    AttendanceBatch,
    AttendanceItem,
    decide_absence_request,
    get_attendance_matrix,
    mark_all_present,
    save_attendance,
    submit_absence_request,
    ThresholdInput,
    update_threshold,
    router as attendance_router,
)
from app.main import app


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def user(db: Session, user_id: int, role_id: int, name: str) -> NguoiDung:
    person = NguoiDung(
        NguoiDungId=user_id,
        HoTen=name,
        Email=f"user{user_id}@example.test",
        MatKhauHash="test-hash",
        TrangThai="HoatDong",
        DaKichHoat=True,
        BatBuocDoiMatKhau=False,
        CanDoiMatKhau=False,
    )
    db.add(person)
    db.flush()
    db.add(NguoiDungVaiTro(NguoiDungId=user_id, VaiTroId=role_id, NgayGan=datetime.now()))
    db.flush()
    return person


def classroom(db: Session):
    teacher = user(db, 10, 3, "Teacher")
    student_a = user(db, 20, 2, "Student A")
    student_b = user(db, 21, 2, "Student B")
    manager = user(db, 30, 7, "Manager")
    program = ChuongTrinhDaoTao(
        ChuongTrinhId=40, MaChuongTrinh="PRG-40", TenChuongTrinh="Program",
        TongThoiLuong=20, HocPhiChuan=0, NgayTao=datetime.now(),
    )
    db.add(program)
    db.flush()
    cls = LopHoc(
        LopHocId=50, MaLop="ATT-50", TenLop="Attendance class", NamHoc="2026-2027",
        ChuongTrinhId=40, GiangVienId=teacher.NguoiDungId, NgayTao=datetime.now(),
    )
    db.add(cls)
    db.flush()
    for person in (student_a, student_b):
        db.add(LopHocHocVien(LopHocId=cls.LopHocId, HocVienId=person.NguoiDungId, NgayThamGia=datetime.now()))
    db.add(AbsenceThreshold(ChuongTrinhId=40, TiLeToiDa=20, NgayCapNhat=datetime.now()))
    db.commit()
    return teacher, student_a, student_b, manager, cls


def test_mark_all_present_creates_auditable_records(db):
    teacher, _, _, _, cls = classroom(db)
    response = mark_all_present(cls.LopHocId, date.today(), teacher, db)
    assert response["counts"] == {"present": 2, "absent": 0, "unexcused": 0, "total": 2}
    assert db.query(AttendanceRecord).count() == 2
    assert db.query(AttendanceAudit).count() == 2


def test_threshold_crossing_flags_and_notifies_teacher_and_manager(db):
    teacher, student, _, manager, cls = classroom(db)
    save_attendance(cls.LopHocId, AttendanceBatch(date=date.today(), records=[
        AttendanceItem(studentId=student.NguoiDungId, status="unexcused_absence"),
    ]), teacher, db)
    notices = db.query(AttendanceNotification).filter(
        AttendanceNotification.HocVienId == student.NguoiDungId,
        AttendanceNotification.Loai == "absence_threshold",
    ).all()
    assert {notice.NguoiNhanId for notice in notices} == {teacher.NguoiDungId, manager.NguoiDungId}
    matrix = get_attendance_matrix(cls.LopHocId, date.today(), teacher, db)
    assert matrix["aboveThreshold"] is True


def test_only_manager_can_edit_past_attendance(db):
    teacher, student, _, manager, cls = classroom(db)
    payload = AttendanceBatch(date=date.today() - timedelta(days=1), records=[
        AttendanceItem(studentId=student.NguoiDungId, status="present"),
    ])
    with pytest.raises(HTTPException) as error:
        save_attendance(cls.LopHocId, payload, teacher, db)
    assert error.value.status_code == 403
    response = save_attendance(cls.LopHocId, payload, manager, db)
    assert response["date"] == payload.attendance_date.isoformat()


def test_approved_absence_request_marks_excused_and_notifies_student(db):
    teacher, student, _, _, cls = classroom(db)
    created = submit_absence_request(
        AbsenceRequestInput(classId=cls.LopHocId, date=date.today(), reason="Medical appointment"),
        student,
        db,
    )
    result = decide_absence_request(
        created["requestId"], AbsenceDecision(decision="approved", reason="Approved"), teacher, db,
    )
    record = db.query(AttendanceRecord).filter(AttendanceRecord.HocVienId == student.NguoiDungId).one()
    assert result["status"] == "approved"
    assert record.TrangThai == "excused_absence"
    assert db.query(AttendanceNotification).filter(
        AttendanceNotification.NguoiNhanId == student.NguoiDungId,
        AttendanceNotification.Loai == "absence_request_approved",
    ).count() == 1
    assert db.query(AttendanceAudit).filter(AttendanceAudit.DoiTuong == "absence_request").count() == 2


def test_lowering_program_threshold_notifies_existing_flagged_student(db):
    teacher, student, _, manager, cls = classroom(db)
    threshold = db.query(AbsenceThreshold).filter(AbsenceThreshold.ChuongTrinhId == cls.ChuongTrinhId).one()
    threshold.TiLeToiDa = 60
    db.add_all([
        AttendanceRecord(LopHocId=cls.LopHocId, HocVienId=student.NguoiDungId,
                         NgayHoc=date.today() - timedelta(days=2), TrangThai="unexcused_absence",
                         NguoiCapNhatId=teacher.NguoiDungId, NgayCapNhat=datetime.now()),
        AttendanceRecord(LopHocId=cls.LopHocId, HocVienId=student.NguoiDungId,
                         NgayHoc=date.today() - timedelta(days=1), TrangThai="present",
                         NguoiCapNhatId=teacher.NguoiDungId, NgayCapNhat=datetime.now()),
    ])
    db.commit()
    update_threshold(cls.ChuongTrinhId, ThresholdInput(percentage=40), manager, db)
    assert {row.NguoiNhanId for row in db.query(AttendanceNotification).filter(
        AttendanceNotification.HocVienId == student.NguoiDungId,
        AttendanceNotification.Loai == "absence_threshold",
    ).all()} == {teacher.NguoiDungId, manager.NguoiDungId}




def test_attendance_routes_cover_workflows():
    paths = {route.path for route in attendance_router.routes}
    assert "/attendance/classes/{class_id}/matrix" in paths
    assert "/attendance/classes/{class_id}/mark-all-present" in paths
    assert "/attendance/absence-requests/{request_id}/decision" in paths
    assert "/attendance/my-history" in paths
    assert "/attendance/classes/{class_id}/export" in paths
    assert "/attendance/notifications" in paths

    app_paths = set(app.openapi()["paths"])
    assert "/attendance/absence-requests" in app_paths
    assert "/attendance/sessions/absence-requests" in app_paths
    assert "/attendance/sessions/absence-requests/with-evidence" in app_paths
