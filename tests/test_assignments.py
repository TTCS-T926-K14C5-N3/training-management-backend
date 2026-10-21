from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.assignment import (
    Assignment,
    AssignmentNotification,
    AssignmentSubmission,
)
from app.models.lich_hoc import LichHoc
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.phong_hoc import PhongHoc
from app.models.program_subject import BuoiHoc
from app.models.vai_tro import VaiTro
from app.routers.assignments import (
    assignment_roster,
    list_assignment_notifications,
    publish_assignment,
)
from app.schemas.assignment import AssignmentWrite, RepositoryUrl
from app.services.assignment_service import MAX_UPLOAD_BYTES, ensure_upload_size, local_now


@pytest.fixture
def assignment_context():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for role_id in (2, 3):
        session.add(VaiTro(VaiTroId=role_id, TenVaiTro=f"Role {role_id}"))
    teacher = NguoiDung(
        NguoiDungId=3,
        HoTen="Teacher",
        Email="teacher@example.org",
        MatKhauHash="hash",
        TrangThai="HoatDong",
    )
    student = NguoiDung(
        NguoiDungId=20,
        HoTen="Student",
        Email="student@example.org",
        MatKhauHash="hash",
        TrangThai="HoatDong",
    )
    session.add_all([teacher, student])
    session.flush()
    session.add_all([
        NguoiDungVaiTro(NguoiDungId=3, VaiTroId=3, NgayGan=datetime.now()),
        NguoiDungVaiTro(NguoiDungId=20, VaiTroId=2, NgayGan=datetime.now()),
    ])
    subject = MonHoc(
        MonHocId=8,
        MaMonHoc="ASG-01",
        TenMonHoc="Assignments",
        SoTinChi=3,
        SoBuoi=4,
        TrongSo=1,
        TrangThai="Đang hoạt động",
    )
    class_record = LopHoc(
        LopHocId=4,
        MaLop="ASG-CLASS",
        TenLop="Assignment class",
        NamHoc="2026-2027",
        GiangVienId=teacher.NguoiDungId,
        NgayKhaiGiang=date.today(),
        SiSoToiDa=30,
        HinhThuc="Trực tiếp",
        TienDo=0,
        TrangThai="Đang học",
        NgayTao=datetime.now(),
    )
    room = PhongHoc(
        PhongHocId=1,
        MaPhong="ASG-ROOM",
        TenPhong="Assignment room",
        SucChua=30,
        TrangThai="Đang hoạt động",
    )
    session.add_all([subject, class_record, room])
    session.flush()
    session.add(LopHocMonHoc(LopHocId=4, MonHocId=8))
    lesson = LichHoc(
        LichHocId=12,
        LopHocId=4,
        MonHocId=8,
        NgayHoc=date.today(),
        GioBatDau=time(9),
        GioKetThuc=time(10),
        PhongHocId=room.PhongHocId,
        GiangVienId=teacher.NguoiDungId,
        TrangThai="Đã lên lịch",
        NgayTao=datetime.now(),
        NguoiTaoId=teacher.NguoiDungId,
        NgayCapNhat=datetime.now(),
        NguoiCapNhatId=teacher.NguoiDungId,
    )
    session.add(lesson)
    now = local_now()
    session.add_all([
        LopHocHocVien(
            LopHocId=4,
            HocVienId=20,
            NgayThamGia=now - timedelta(days=1),
            TrangThaiGhiDanh="Đang học",
        ),
        Assignment(
            AssignmentId=1,
            LopHocId=4,
            MonHocId=8,
            LichHocId=12,
            GiangVienId=3,
            TieuDe="New task",
            MoTa="Task description",
            HanNop=now + timedelta(days=1),
            DiemToiDa=Decimal("10"),
            ChoNopMuon=True,
            TrangThai="Draft",
            NgayTao=now,
            NgayCapNhat=now,
        ),
    ])
    session.commit()
    try:
        yield session, teacher, student
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_assignment_write_accepts_linked_lesson_and_late_policy():
    assignment = AssignmentWrite.model_validate({
        "lopHocId": 4,
        "monHocId": 8,
        "lichHocId": 12,
        "tieuDe": "  Bài thực hành  ",
        "moTa": "  Hoàn thiện API và gửi liên kết repository.  ",
        "hanNop": "2027-01-10T16:00:00+07:00",
        "diemToiDa": "25.50",
        "choNopMuon": True,
    })
    assert assignment.tieu_de == "Bài thực hành"
    assert assignment.mo_ta.startswith("Hoàn thiện")
    assert assignment.diem_toi_da == Decimal("25.50")
    assert assignment.cho_nop_muon is True
    assert assignment.han_nop.tzinfo is not None


@pytest.mark.parametrize("url", [
    "http://github.com/user/repo",
    "https://github.com",
    "https://user:secret@example.com/repo",
    "javascript:alert(1)",
    "https://example.com/",
])
def test_repository_url_rejects_invalid_or_non_repository_urls(url: str):
    with pytest.raises(ValidationError):
        RepositoryUrl(url=url)


def test_repository_url_accepts_https_path():
    assert RepositoryUrl(url=" https://git.example.org/team/project.git ").url == "https://git.example.org/team/project.git"


def test_assignment_rejects_blank_description_and_nonpositive_points():
    base = {
        "lopHocId": 1,
        "monHocId": 2,
        "lichHocId": 3,
        "tieuDe": "Test",
        "moTa": "Description",
        "hanNop": datetime(2027, 1, 1),
        "diemToiDa": 10,
    }
    with pytest.raises(ValidationError):
        AssignmentWrite.model_validate({**base, "moTa": "   "})
    with pytest.raises(ValidationError):
        AssignmentWrite.model_validate({**base, "diemToiDa": 0})


def test_upload_size_limit_accepts_exactly_twenty_mebibytes():
    assert MAX_UPLOAD_BYTES == 20 * 1024 * 1024
    ensure_upload_size(MAX_UPLOAD_BYTES)


def test_upload_size_limit_rejects_over_twenty_mebibytes():
    with pytest.raises(HTTPException) as error:
        ensure_upload_size(MAX_UPLOAD_BYTES + 1)
    assert error.value.status_code == 413


def test_publishing_notifies_active_students_and_notifications_are_private(assignment_context):
    db, teacher, student = assignment_context
    publish_assignment(1, db, teacher)

    notices = list_assignment_notifications(db, student)

    assert len(notices) == 1
    assert notices[0]["type"] == "published"
    assert notices[0]["assignmentId"] == 1
    assert db.query(AssignmentNotification).count() == 1


def test_assignment_roster_can_filter_ungraded_submissions(assignment_context):
    db, teacher, student = assignment_context
    assignment = db.query(Assignment).filter(Assignment.AssignmentId == 1).one()
    assignment.TrangThai = "Published"
    db.add(
        AssignmentSubmission(
            AssignmentId=1,
            HocVienId=student.NguoiDungId,
            VersionNumber=1,
            RepositoryUrl="https://github.com/team/project",
            SubmittedAt=local_now(),
            SubmissionStatus="Submitted",
        )
    )
    db.commit()

    roster = assignment_roster(1, "ungraded", db, teacher)

    assert roster["totalStudents"] == 1
    assert [item["studentId"] for item in roster["students"]] == [student.NguoiDungId]
