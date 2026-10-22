import asyncio
import json
from io import BytesIO
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import mssql
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
    assignment_options,
    create_assignment,
    _teacher_assignments_query,
    list_my_assignments,
    list_my_submission_history,
    list_student_submission_history,
    list_teacher_assignments,
    list_assignment_notifications,
    publish_assignment,
)
from app.schemas.assignment import AssignmentWrite, RepositoryUrl
from app.services.assignment_service import (
    MAX_UPLOAD_BYTES,
    ensure_enrolled,
    ensure_upload_size,
    local_now,
    save_uploads,
)


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


def test_saved_upload_name_fits_database_column(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.assignment_service.UPLOAD_ROOT", tmp_path)
    uploaded_file = UploadFile(
        filename="BÀI TẬP.docx",
        file=BytesIO(b"assignment"),
    )

    stored = asyncio.run(save_uploads([uploaded_file]))

    assert len(stored[0]["stored_name"]) == 36
    assert (tmp_path / stored[0]["stored_name"]).read_bytes() == b"assignment"


def test_create_assignment_rejects_past_deadline_before_saving_files(assignment_context, monkeypatch):
    db, teacher, _ = assignment_context

    async def fail_if_uploads_are_saved(_files):
        pytest.fail("Uploads must not be saved for an invalid deadline.")

    monkeypatch.setattr("app.routers.assignments.save_uploads", fail_if_uploads_are_saved)
    payload = {
        "lopHocId": 4,
        "monHocId": 8,
        "lichHocId": 12,
        "tieuDe": "Bài tập mới",
        "moTa": "Mô tả bài tập",
        "hanNop": (local_now() - timedelta(minutes=1)).isoformat(),
        "diemToiDa": 10,
    }

    with pytest.raises(HTTPException) as error:
        asyncio.run(create_assignment(json.dumps(payload), [], db, teacher))

    assert error.value.status_code == 422
    assert db.query(Assignment).count() == 1


def test_create_assignment_saves_future_deadline_as_draft(assignment_context, monkeypatch):
    db, teacher, _ = assignment_context

    async def no_uploads(_files):
        return []

    monkeypatch.setattr("app.routers.assignments.save_uploads", no_uploads)
    payload = {
        "lopHocId": 4,
        "monHocId": 8,
        "lichHocId": 12,
        "tieuDe": "Bài tập mới",
        "moTa": "Mô tả bài tập",
        "hanNop": (local_now() + timedelta(days=2)).isoformat(),
        "diemToiDa": 10,
    }

    result = asyncio.run(create_assignment(json.dumps(payload), [], db, teacher))

    assert result["trangThai"] == "Draft"
    assert result["hanNop"] > local_now().isoformat()


def test_publishing_notifies_active_students_and_notifications_are_private(assignment_context):
    db, teacher, student = assignment_context
    inactive_student = NguoiDung(
        NguoiDungId=21,
        HoTen="Paused student",
        Email="paused@example.org",
        MatKhauHash="hash",
        TrangThai="HoatDong",
    )
    db.add(inactive_student)
    db.add(LopHocHocVien(
        LopHocId=4,
        HocVienId=21,
        NgayThamGia=local_now() - timedelta(days=1),
        TrangThaiGhiDanh="Bảo lưu",
    ))
    db.commit()

    publish_assignment(1, db, teacher)

    notices = list_assignment_notifications(db, student)

    assert len(notices) == 1
    assert notices[0]["type"] == "published"
    assert notices[0]["assignmentId"] == 1
    assert db.query(AssignmentNotification).count() == 1


def test_assignment_options_loads_assigned_class_subject_and_lessons(assignment_context):
    db, teacher, _ = assignment_context
    db.refresh(teacher)

    statement_count = []
    engine = db.get_bind()

    def count_statement(*_args):
        statement_count.append(1)

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        options = assignment_options(db, teacher)
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)

    assert len(options) == 1
    assert options[0]["lopHocId"] == 4
    assert options[0]["subjects"][0]["monHocId"] == 8
    assert options[0]["subjects"][0]["lessons"][0]["lichHocId"] == 12
    assert len(statement_count) <= 4


def test_teacher_assignment_list_returns_assignment_payload(assignment_context):
    db, teacher, _ = assignment_context
    template = db.query(Assignment).filter(Assignment.AssignmentId == 1).one()
    db.add_all([
        Assignment(
            AssignmentId=assignment_id,
            LopHocId=template.LopHocId,
            MonHocId=template.MonHocId,
            LichHocId=template.LichHocId,
            GiangVienId=template.GiangVienId,
            TieuDe=f"Task {assignment_id}",
            MoTa=template.MoTa,
            HanNop=template.HanNop,
            DiemToiDa=template.DiemToiDa,
            ChoNopMuon=template.ChoNopMuon,
            TrangThai=template.TrangThai,
            NgayTao=template.NgayTao,
            NgayCapNhat=template.NgayCapNhat,
        )
        for assignment_id in range(2, 22)
    ])
    db.commit()
    statement_count = []
    engine = db.get_bind()

    def count_statement(*_args):
        statement_count.append(1)

    event.listen(engine, "before_cursor_execute", count_statement)

    try:
        assignments = list_teacher_assignments(db, teacher)
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)

    assert len(assignments) == 21
    assert assignments[0]["assignmentId"] == 1
    assert assignments[0]["tenLop"] == "Assignment class"
    assert assignments[0]["tenMonHoc"] == "Assignments"
    assert assignments[0]["attachments"] == []
    assert len(statement_count) <= 10


def test_teacher_assignment_query_uses_sql_server_compatible_assignment_scope(assignment_context):
    db, teacher, _ = assignment_context
    query = _teacher_assignments_query(db, teacher)
    assert query is not None
    sql = str(query.statement.compile(dialect=mssql.dialect()))

    assert "EXISTS (SELECT" in sql
    assert "[LopHoc_MonHoc_GiangVien].[MonHocId] = [Assignment].[MonHocId]" in sql
    assert ") IN (" not in sql


def test_paused_student_is_excluded_from_assignments_and_roster(assignment_context):
    db, teacher, student = assignment_context
    enrollment = db.query(LopHocHocVien).filter(
        LopHocHocVien.HocVienId == student.NguoiDungId
    ).one()
    enrollment.TrangThaiGhiDanh = "Bảo lưu"
    assignment = db.query(Assignment).filter(Assignment.AssignmentId == 1).one()
    assignment.TrangThai = "Published"

    with pytest.raises(HTTPException) as error:
        ensure_enrolled(db, 4, student.NguoiDungId)

    assert error.value.status_code == 403
    assert list_my_assignments(db, student) == []
    assert assignment_roster(1, "all", db, teacher)["totalStudents"] == 0


def test_student_can_view_all_submission_versions_in_order(assignment_context):
    db, _, student = assignment_context
    assignment = db.query(Assignment).filter(Assignment.AssignmentId == 1).one()
    assignment.TrangThai = "Published"
    submitted_at = local_now()
    db.add_all([
        AssignmentSubmission(
            AssignmentId=1,
            HocVienId=student.NguoiDungId,
            VersionNumber=version,
            RepositoryUrl=f"https://github.com/student/project-v{version}",
            SubmittedAt=submitted_at + timedelta(minutes=version),
            SubmissionStatus="Submitted",
        )
        for version in (1, 2, 3)
    ])
    db.commit()

    history = list_my_submission_history(1, db, student)

    assert [item["version"] for item in history] == [1, 2, 3]
    assert [item["repositoryUrl"] for item in history] == [
        "https://github.com/student/project-v1",
        "https://github.com/student/project-v2",
        "https://github.com/student/project-v3",
    ]
    assert all(item["attachments"] == [] for item in history)


def test_assigned_teacher_can_view_student_submission_history(assignment_context):
    db, teacher, student = assignment_context
    assignment = db.query(Assignment).filter(Assignment.AssignmentId == 1).one()
    assignment.TrangThai = "Published"
    submitted_at = local_now()
    db.add_all([
        AssignmentSubmission(
            AssignmentId=1,
            HocVienId=student.NguoiDungId,
            VersionNumber=version,
            RepositoryUrl=f"https://github.com/student/project-v{version}",
            SubmittedAt=submitted_at + timedelta(minutes=version),
            SubmissionStatus="Submitted",
        )
        for version in (1, 2, 3)
    ])
    db.commit()

    history = list_student_submission_history(1, student.NguoiDungId, db, teacher)

    assert [item["version"] for item in history] == [1, 2, 3]
    assert [item["submissionId"] for item in history] == sorted(
        item["submissionId"] for item in history
    )


def test_unassigned_teacher_cannot_view_submission_history(assignment_context):
    db, _, student = assignment_context
    other_teacher = NguoiDung(
        NguoiDungId=4,
        HoTen="Other Teacher",
        Email="other-teacher@example.org",
        MatKhauHash="hash",
        TrangThai="HoatDong",
    )
    db.add(other_teacher)
    db.add(NguoiDungVaiTro(NguoiDungId=4, VaiTroId=3, NgayGan=datetime.now()))
    db.commit()

    with pytest.raises(HTTPException) as error:
        list_student_submission_history(1, student.NguoiDungId, db, other_teacher)

    assert error.value.status_code == 403


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
