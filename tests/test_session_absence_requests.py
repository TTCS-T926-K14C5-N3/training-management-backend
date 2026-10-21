from datetime import date, datetime, time, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.absence_request import (
    AbsenceRequest,
    AttendanceAudit,
    AttendanceNotification,
)
from app.models.diem_danh_buoi_hoc import DiemDanhBuoiHoc
from app.models.lich_hoc import LichHoc
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.phong_hoc import PhongHoc
from app.models.vai_tro import VaiTro
from app.routers.attendance_sessions import (
    _create_absence_request,
    decide_absence_request,
    get_pending_approved_absence_alert,
    list_absence_requests,
    mark_attendance_notification_read,
)
from app.routers import attendance_sessions
from app.schemas.attendance import AbsenceRequestDecision, AbsenceRequestWrite


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


def add_user(db, user_id: int, role_id: int, name: str) -> NguoiDung:
    if db.get(VaiTro, role_id) is None:
        db.add(VaiTro(VaiTroId=role_id, TenVaiTro=f"Vai trò {role_id}"))
    person = NguoiDung(
        NguoiDungId=user_id,
        HoTen=name,
        Email=f"absence-{user_id}@example.test",
        MatKhauHash="test-hash",
        TrangThai="HoatDong",
        DaKichHoat=True,
        BatBuocDoiMatKhau=False,
        CanDoiMatKhau=False,
    )
    db.add(person)
    db.flush()
    db.add(
        NguoiDungVaiTro(
            NguoiDungId=user_id,
            VaiTroId=role_id,
            NgayGan=datetime.now(),
        )
    )
    db.flush()
    return person


def absence_context(db, *, assigned_teacher_id: int = 10):
    teacher = add_user(db, 10, 3, "Giảng viên A")
    assigned_teacher = (
        teacher
        if assigned_teacher_id == teacher.NguoiDungId
        else add_user(db, assigned_teacher_id, 3, "Giảng viên B")
    )
    student = add_user(db, 20, 2, "Học viên A")
    room = PhongHoc(
        MaPhong="ABS-101",
        TenPhong="Phòng xin phép",
        SucChua=30,
        TrangThai="Đang hoạt động",
    )
    subject = MonHoc(
        MaMonHoc="ABS-101",
        TenMonHoc="Môn thử nghiệm",
        SoTinChi=3,
        SoBuoi=10,
        TrongSo=1,
        TrangThai="Đang hoạt động",
    )
    db.add_all([room, subject])
    db.flush()
    class_record = LopHoc(
        MaLop="ABS-101",
        TenLop="Lớp xin phép",
        NamHoc="2026-2027",
        GiangVienId=teacher.NguoiDungId,
        NgayKhaiGiang=date.today(),
        SiSoToiDa=30,
        HinhThuc="Trực tiếp",
        PhongHocId=room.PhongHocId,
        TienDo=0,
        TrangThai="Đang học",
        NgayTao=datetime.now(),
    )
    db.add(class_record)
    db.flush()
    schedule = LichHoc(
        LopHocId=class_record.LopHocId,
        MonHocId=subject.MonHocId,
        NgayHoc=date.today() + timedelta(days=10),
        GioBatDau=time(9),
        GioKetThuc=time(10),
        PhongHocId=room.PhongHocId,
        GiangVienId=assigned_teacher.NguoiDungId,
        TrangThai="Đã lên lịch",
        NgayTao=datetime.now(),
        NguoiTaoId=teacher.NguoiDungId,
        NgayCapNhat=datetime.now(),
        NguoiCapNhatId=teacher.NguoiDungId,
    )
    db.add_all(
        [
            schedule,
            LopHocHocVien(
                LopHocId=class_record.LopHocId,
                HocVienId=student.NguoiDungId,
                NgayThamGia=datetime.combine(
                    date.today() - timedelta(days=1),
                    time.min,
                ),
                TrangThaiGhiDanh="Đang học",
            ),
        ]
    )
    db.commit()
    return teacher, assigned_teacher, student, schedule


def test_approved_request_updates_attendance_and_notifies_student(
    db,
    monkeypatch,
):
    sent_emails = []
    monkeypatch.setattr(
        attendance_sessions,
        "send_absence_request_approved_email",
        lambda *args: sent_emails.append(args),
    )
    teacher, _, student, schedule = absence_context(db)
    request = _create_absence_request(
        db,
        AbsenceRequestWrite(scheduleId=schedule.LichHocId, reason="Lý do sức khỏe"),
        student,
    )
    assert db.query(DiemDanhBuoiHoc).filter(
        DiemDanhBuoiHoc.LichHocId == schedule.LichHocId,
        DiemDanhBuoiHoc.HocVienId == student.NguoiDungId,
    ).count() == 0
    listed = list_absence_requests(teacher, db)
    assert listed[0]["scheduleId"] == schedule.LichHocId
    assert listed[0]["subjectName"] == "Môn thử nghiệm"

    result = decide_absence_request(
        request["requestId"],
        AbsenceRequestDecision(
            decision="approved",
            reason="Đã kiểm tra và chấp thuận",
        ),
        teacher,
        db,
    )

    attendance = db.query(DiemDanhBuoiHoc).filter(
        DiemDanhBuoiHoc.LichHocId == schedule.LichHocId,
        DiemDanhBuoiHoc.HocVienId == student.NguoiDungId,
    ).one()
    assert result["status"] == "approved"
    assert attendance.TrangThai == "Vắng có phép"
    assert attendance.GhiChu == "Đã kiểm tra và chấp thuận"
    assert db.query(AttendanceAudit).filter(
        AttendanceAudit.LichHocId == schedule.LichHocId
    ).count() == 1
    notification = db.query(AttendanceNotification).filter(
        AttendanceNotification.NguoiNhanId == student.NguoiDungId
    ).one()
    assert "đã được duyệt" in notification.NoiDung
    assert sent_emails == [
        (
            student.Email,
            student.HoTen,
            "ABS-101",
            "Môn thử nghiệm",
            schedule.NgayHoc.isoformat(),
            "09:00",
            "10:00",
            "Đã kiểm tra và chấp thuận",
        )
    ]


def test_student_approval_alert_is_cleared_after_following_request(
    db,
    monkeypatch,
):
    monkeypatch.setattr(
        attendance_sessions,
        "send_absence_request_approved_email",
        lambda *_args: None,
    )
    teacher, _, student, schedule = absence_context(db)
    request = _create_absence_request(
        db,
        AbsenceRequestWrite(scheduleId=schedule.LichHocId, reason="Lý do sức khỏe"),
        student,
    )
    decide_absence_request(
        request["requestId"],
        AbsenceRequestDecision(
            decision="approved",
            reason="Đã kiểm tra và chấp thuận",
        ),
        teacher,
        db,
    )

    alert = get_pending_approved_absence_alert(student, db)
    assert alert is not None
    assert "đã được duyệt" in alert["message"]

    mark_attendance_notification_read(alert["id"], student, db)

    assert get_pending_approved_absence_alert(student, db) is None


def test_teacher_request_list_is_scoped_to_the_assigned_session(db):
    class_teacher, _, student, schedule = absence_context(
        db,
        assigned_teacher_id=11,
    )
    _create_absence_request(
        db,
        AbsenceRequestWrite(scheduleId=schedule.LichHocId, reason="Lý do sức khỏe"),
        student,
    )

    assert list_absence_requests(class_teacher, db) == []


def test_assigned_session_teacher_can_review_even_if_not_class_teacher(db):
    _, assigned_teacher, student, schedule = absence_context(
        db,
        assigned_teacher_id=11,
    )
    request = _create_absence_request(
        db,
        AbsenceRequestWrite(scheduleId=schedule.LichHocId, reason="Lý do sức khỏe"),
        student,
    )

    visible_requests = list_absence_requests(assigned_teacher, db)
    result = decide_absence_request(
        request["requestId"],
        AbsenceRequestDecision(
            decision="approved",
            reason="Đã nhận và xác minh",
        ),
        assigned_teacher,
        db,
    )

    assert [item["requestId"] for item in visible_requests] == [request["requestId"]]
    assert result["status"] == "approved"
    assert db.query(DiemDanhBuoiHoc).one().TrangThai == "Vắng có phép"


def test_duplicate_request_for_same_session_is_rejected(db):
    _, _, student, schedule = absence_context(db)
    request_data = AbsenceRequestWrite(
        scheduleId=schedule.LichHocId,
        reason="Lý do sức khỏe",
    )
    _create_absence_request(db, request_data, student)

    with pytest.raises(HTTPException) as error:
        _create_absence_request(db, request_data, student)

    assert error.value.status_code == 409


def test_request_evidence_is_stored_with_generated_name(db, tmp_path, monkeypatch):
    _, _, student, schedule = absence_context(db)
    monkeypatch.setattr(attendance_sessions, "EVIDENCE_DIRECTORY", tmp_path)

    request = _create_absence_request(
        db,
        AbsenceRequestWrite(scheduleId=schedule.LichHocId, reason="Lý do sức khỏe"),
        student,
        evidence=(b"%PDF-1.7\nproof", "giay-kham.pdf", "application/pdf"),
    )

    stored = db.query(AbsenceRequest).one()
    assert request["evidence"]
    assert request["evidenceName"] == "giay-kham.pdf"
    assert stored.TepMinhChungPath != "giay-kham.pdf"
    assert (tmp_path / stored.TepMinhChungPath).read_bytes().startswith(b"%PDF-")


def test_class_teacher_cannot_review_session_assigned_to_another_teacher(db):
    class_teacher, _, student, schedule = absence_context(
        db,
        assigned_teacher_id=11,
    )
    request = _create_absence_request(
        db,
        AbsenceRequestWrite(scheduleId=schedule.LichHocId, reason="Lý do sức khỏe"),
        student,
    )

    with pytest.raises(HTTPException) as error:
        decide_absence_request(
            request["requestId"],
            AbsenceRequestDecision(decision="rejected", reason="Chưa đủ căn cứ"),
            class_teacher,
            db,
        )

    assert error.value.status_code == 403
    assert db.query(AbsenceRequest).one().TrangThai == "Chờ duyệt"
