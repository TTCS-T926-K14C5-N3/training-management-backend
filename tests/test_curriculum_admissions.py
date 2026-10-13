from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.database import Base
from app.models.admissions import Lead, LeadAssignmentHistory, LeadConversion
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.mon_hoc import MonHoc
from app.models.vai_tro import VaiTro
from app.routers.academic import (
    archive_subject,
    clone_program_subject_sessions,
    create_subject,
    get_program_subject_sessions,
    get_program_subjects,
    list_subjects,
    replace_program_subject_sessions,
    replace_program_subjects,
)
from app.routers.admissions import (
    _public_submissions,
    _get_visible_lead,
    bulk_assign_leads,
    create_lead,
    convert_lead_to_student,
    get_lead_assignments,
    list_admissions_consultants,
    list_leads,
    replace_lead_assignments,
    submit_public_lead,
    update_lead,
)
from app.schemas.academic import SubjectCreate
from app.schemas.admissions import (
    BulkLeadAssignmentsWrite,
    LeadAssignmentsWrite,
    LeadWrite,
    PublicLeadCreate,
)
from app.schemas.curriculum import (
    ProgramSubjectsWrite,
    SessionCloneWrite,
    SessionsWrite,
)
from app.services.rbac_service import DEFAULT_ROLE_PERMISSIONS


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


def add_user(db: Session, user_id: int, role_id: int, name: str) -> NguoiDung:
    if db.query(VaiTro).filter(VaiTro.VaiTroId == role_id).first() is None:
        db.add(VaiTro(VaiTroId=role_id, TenVaiTro=f"Vai trò {role_id}"))
    user = NguoiDung(
        NguoiDungId=user_id,
        HoTen=name,
        Email=f"user{user_id}@example.com",
        SoDienThoai=f"0900000{user_id:03}",
        MatKhauHash="unused",
        TrangThai="HoatDong",
        DaKichHoat=True,
        BatBuocDoiMatKhau=False,
        CanDoiMatKhau=False,
    )
    db.add(user)
    db.flush()
    db.add(
        NguoiDungVaiTro(
            NguoiDungId=user_id,
            VaiTroId=role_id,
            NgayGan=datetime.now(),
        )
    )
    db.commit()
    return user


def add_program(db: Session, program_id: int = 1) -> ChuongTrinhDaoTao:
    program = ChuongTrinhDaoTao(
        ChuongTrinhId=program_id,
        MaChuongTrinh=f"PRG{program_id}",
        TenChuongTrinh=f"Chương trình {program_id}",
        TongThoiLuong=10,
        HocPhiChuan=100,
        TrangThai="Đang áp dụng",
        NgayTao=datetime.now(),
    )
    db.add(program)
    db.commit()
    return program


def test_default_permissions_match_curriculum_and_lead_role_boundaries():
    assert {
        "LEAD_VIEW",
        "LEAD_CREATE",
        "LEAD_UPDATE",
    } <= set(DEFAULT_ROLE_PERMISSIONS[5])
    assert not {"LEAD_DELETE", "LEAD_ASSIGN"} & set(DEFAULT_ROLE_PERMISSIONS[5])
    assert {
        "CURRICULUM_VIEW",
        "CURRICULUM_CREATE",
        "CURRICULUM_UPDATE",
        "CURRICULUM_DELETE",
        "LEAD_VIEW",
        "LEAD_CREATE",
        "LEAD_UPDATE",
        "LEAD_DELETE",
        "LEAD_ASSIGN",
    } <= set(DEFAULT_ROLE_PERMISSIONS[7])
    assert set(DEFAULT_ROLE_PERMISSIONS[8]) >= set(DEFAULT_ROLE_PERMISSIONS[7])


def test_program_subjects_preserve_order_prerequisite_and_session_limit(db: Session):
    add_program(db)
    first = create_subject(
        SubjectCreate(
            maMonHoc="SUB1",
            tenMonHoc="Môn một",
            soBuoi=2,
            trongSo=0.4,
            moTaChuanDauRa="Mục tiêu đầu ra",
        ),
        db,
    )
    second = create_subject(
        SubjectCreate(maMonHoc="SUB2", tenMonHoc="Môn hai", soBuoi=1),
        db,
    )

    rows = replace_program_subjects(
        1,
        ProgramSubjectsWrite(
            subjects=[
                {"monHocId": second["monHocId"], "thuTu": 2, "monTienQuyetId": first["monHocId"]},
                {"monHocId": first["monHocId"], "thuTu": 1},
            ]
        ),
        db,
    )
    assert [row["monHocId"] for row in rows] == [first["monHocId"], second["monHocId"]]
    assert rows[1]["monTienQuyetId"] == first["monHocId"]
    assert rows[0]["soBuoi"] == 2
    assert float(db.query(MonHoc).filter_by(
        MonHocId=first["monHocId"]
    ).one().TrongSo) == 0.4
    reordered = replace_program_subjects(
        1,
        ProgramSubjectsWrite(
            subjects=[
                {"monHocId": first["monHocId"], "thuTu": 2},
                {"monHocId": second["monHocId"], "thuTu": 1, "monTienQuyetId": first["monHocId"]},
            ]
        ),
        db,
    )
    assert [row["monHocId"] for row in reordered] == [
        second["monHocId"],
        first["monHocId"],
    ]

    result = replace_program_subject_sessions(
        1,
        first["monHocId"],
        SessionsWrite(
            sessions=[
                {"soThuTu": 1, "chuDe": "Giới thiệu", "mucTieu": "Hiểu nội dung"},
                {"soThuTu": 2, "chuDe": "Thực hành"},
            ]
        ),
        db,
    )
    assert [session["soThuTu"] for session in result["sessions"]] == [1, 2]
    assert get_program_subject_sessions(1, first["monHocId"], db)["sessions"][0][
        "chuDe"
    ] == "Giới thiệu"

    with pytest.raises(HTTPException) as error:
        replace_program_subject_sessions(
            1,
            first["monHocId"],
            SessionsWrite(
                sessions=[
                    {"soThuTu": 1, "chuDe": "Một"},
                    {"soThuTu": 2, "chuDe": "Hai"},
                    {"soThuTu": 3, "chuDe": "Ba"},
                ]
            ),
            db,
        )
    assert error.value.status_code == 422


def test_clone_program_subject_sessions(db: Session):
    add_program(db)
    first = create_subject(
        SubjectCreate(maMonHoc="CLONE1", tenMonHoc="Môn nguồn", soBuoi=3),
        db,
    )
    second = create_subject(
        SubjectCreate(maMonHoc="CLONE2", tenMonHoc="Môn đích", soBuoi=2),
        db,
    )
    third = create_subject(
        SubjectCreate(maMonHoc="CLONE3", tenMonHoc="Môn chưa có buổi", soBuoi=2),
        db,
    )
    replace_program_subjects(
        1,
        ProgramSubjectsWrite(
            subjects=[
                {"monHocId": first["monHocId"], "thuTu": 1},
                {"monHocId": second["monHocId"], "thuTu": 2},
                {"monHocId": third["monHocId"], "thuTu": 3},
            ]
        ),
        db,
    )

    # Save 3 sessions for first subject
    replace_program_subject_sessions(
        1,
        first["monHocId"],
        SessionsWrite(
            sessions=[
                {"soThuTu": 1, "chuDe": "Buổi 1 lý thuyết", "mucTieu": "Nắm vững lý thuyết"},
                {"soThuTu": 2, "chuDe": "Buổi 2 thực hành", "mucTieu": "Làm bài tập thực tế"},
                {"soThuTu": 3, "chuDe": "Buổi 3 kiểm tra", "mucTieu": "Đánh giá kết quả"},
            ]
        ),
        db,
    )

    # Clone sessions from first to second (second has SoBuoi=2, so it clamps to 2 sessions)
    cloned = clone_program_subject_sessions(
        1,
        second["monHocId"],
        SessionCloneWrite(sourceSubjectId=first["monHocId"]),
        db,
    )
    assert len(cloned["sessions"]) == 2
    assert cloned["sessions"][0]["chuDe"] == "Buổi 1 lý thuyết"
    assert cloned["sessions"][0]["mucTieu"] == "Nắm vững lý thuyết"
    assert cloned["sessions"][1]["chuDe"] == "Buổi 2 thực hành"
    assert cloned["sessions"][1]["soThuTu"] == 2

    # Clone from third (which has no sessions) -> should raise 400
    with pytest.raises(HTTPException) as err:
        clone_program_subject_sessions(
            1,
            second["monHocId"],
            SessionCloneWrite(sourceSubjectId=third["monHocId"]),
            db,
        )
    assert err.value.status_code == 400

    # Clone from nonexistent subject -> should raise 404
    with pytest.raises(HTTPException) as err:
        clone_program_subject_sessions(
            1,
            second["monHocId"],
            SessionCloneWrite(sourceSubjectId=9999),
            db,
        )
    assert err.value.status_code == 404



def test_program_subject_rejects_self_and_cyclic_prerequisites(db: Session):
    add_program(db)
    one = create_subject(
        SubjectCreate(maMonHoc="C1", tenMonHoc="Một"), db
    )
    two = create_subject(
        SubjectCreate(maMonHoc="C2", tenMonHoc="Hai"), db
    )
    with pytest.raises(HTTPException, match="chính nó"):
        replace_program_subjects(
            1,
            ProgramSubjectsWrite(
                subjects=[
                    {"monHocId": one["monHocId"], "thuTu": 1, "monTienQuyetId": one["monHocId"]}
                ]
            ),
            db,
        )
    with pytest.raises(HTTPException, match="vòng lặp"):
        replace_program_subjects(
            1,
            ProgramSubjectsWrite(
                subjects=[
                    {"monHocId": one["monHocId"], "thuTu": 1, "monTienQuyetId": two["monHocId"]},
                    {"monHocId": two["monHocId"], "thuTu": 2, "monTienQuyetId": one["monHocId"]},
                ]
            ),
            db,
        )


@pytest.mark.parametrize("coefficient", [-0.01, 1.01])
def test_subject_rejects_coefficient_outside_zero_to_one(coefficient: float):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SubjectCreate(
            maMonHoc="BAD",
            tenMonHoc="Hệ số ngoài miền",
            trongSo=coefficient,
        )


def test_used_subject_is_archived_and_keeps_associations(db: Session):
    add_program(db)
    subject = create_subject(
        SubjectCreate(maMonHoc="USED", tenMonHoc="Được sử dụng"), db
    )
    replace_program_subjects(
        1,
        ProgramSubjectsWrite(
            subjects=[{"monHocId": subject["monHocId"], "thuTu": 1}]
        ),
        db,
    )
    archive_subject(subject["monHocId"], db)
    rows = get_program_subjects(1, db)
    assert rows[0]["monHocId"] == subject["monHocId"]
    assert rows[0]["sessions"] == []


def test_subject_list_marks_program_applied_subjects(db: Session):
    add_program(db)
    applied_subject = create_subject(
        SubjectCreate(maMonHoc="APPLIED", tenMonHoc="Môn đã áp dụng"), db
    )
    unused_subject = create_subject(
        SubjectCreate(maMonHoc="UNUSED", tenMonHoc="Môn chưa áp dụng"), db
    )
    replace_program_subjects(
        1,
        ProgramSubjectsWrite(
            subjects=[
                {"monHocId": applied_subject["monHocId"], "thuTu": 1}
            ]
        ),
        db,
    )

    subjects = list_subjects(include_inactive=True, db=db)
    applied_status = {
        subject["monHocId"]: subject["daApDung"] for subject in subjects
    }

    assert applied_status[applied_subject["monHocId"]] is True
    assert applied_status[unused_subject["monHocId"]] is False


def test_public_lead_honeypot_and_submission_response(db: Session):
    add_program(db)
    _public_submissions.clear()

    def http_request(ip: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/admissions/public/leads",
                "headers": [],
                "client": (ip, 1234),
                "server": ("test", 80),
                "scheme": "http",
                "query_string": b"",
            }
        )

    trap_response = submit_public_lead(
        PublicLeadCreate(
            hoTen="Spam", soDienThoai="0901234567", chuongTrinhId=1, website="bot"
        ),
        http_request("192.0.2.20"),
        db,
    )
    assert "1 ngày làm việc" in trap_response["responseTimeAssurance"]
    assert db.query(Lead).count() == 0

    response = submit_public_lead(
        PublicLeadCreate(
            hoTen="Nguyễn An",
            soDienThoai="0901234567",
            email="AN@example.com",
            chuongTrinhId=1,
            nguon="Website",
        ),
        http_request("192.0.2.21"),
        db,
    )
    assert "Cảm ơn" in response["message"]
    assert response["duplicatePhone"] is False
    lead = db.query(Lead).one()
    assert lead.TrangThai == "Mới"
    assert lead.Email == "an@example.com"


def test_internal_lead_can_be_created_without_a_program(db: Session):
    manager = add_user(db, 69, 7, "Manager")
    lead = create_lead(
        LeadWrite(
            hoTen="Nguyễn An",
            soDienThoai="0901234567",
            nguon="Website",
        ),
        manager,
        db,
    )

    assert lead["chuongTrinhId"] is None
    assert lead["tenChuongTrinh"] is None
    assert list_leads(None, None, None, None, None, None, manager, db) == [lead]


def test_lead_conversion_creates_student_once_and_locks_lead(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    manager = add_user(db, 69, 7, "Manager")
    db.add(VaiTro(VaiTroId=2, TenVaiTro="Học viên"))
    db.commit()
    lead = create_lead(
        LeadWrite(
            hoTen="Nguyễn An",
            soDienThoai="0901234567",
            email="an@example.com",
            chuongTrinhId=None,
            nguon="Website",
        ),
        manager,
        db,
    )
    sent_emails: list[dict] = []
    monkeypatch.setattr(
        "app.routers.admissions.send_activation_email",
        lambda **kwargs: sent_emails.append(kwargs),
    )

    result = convert_lead_to_student(lead["leadId"], manager, db)

    assert result["alreadyConverted"] is False
    assert result["emailSent"] is True
    assert result["maHocVien"] == f"HV{result['hocVienId']:06d}"
    assert result["lead"]["trangThai"] == "Đã nhập học"
    student = db.query(NguoiDung).filter(
        NguoiDung.NguoiDungId == result["hocVienId"]
    ).one()
    assert student.HoTen == "Nguyễn An"
    assert student.SoDienThoai == "0901234567"
    assert student.Email == "an@example.com"
    assert db.query(NguoiDungVaiTro).filter_by(
        NguoiDungId=student.NguoiDungId,
        VaiTroId=2,
    ).one()
    assert db.query(LeadConversion).filter_by(
        LeadId=lead["leadId"],
        NguoiDungId=student.NguoiDungId,
    ).one().MaHocVien == result["maHocVien"]
    assert sent_emails[0]["ma_hoc_vien"] == result["maHocVien"]

    repeated_result = convert_lead_to_student(lead["leadId"], manager, db)
    assert repeated_result["alreadyConverted"] is True
    assert repeated_result["hocVienId"] == student.NguoiDungId
    assert len(sent_emails) == 1
    assert db.query(LeadConversion).count() == 1

    with pytest.raises(HTTPException) as assignment_error:
        replace_lead_assignments(
            lead["leadId"],
            LeadAssignmentsWrite(consultantIds=[]),
            manager,
            db,
        )
    assert assignment_error.value.status_code == 409
    with pytest.raises(HTTPException) as bulk_assignment_error:
        bulk_assign_leads(
            BulkLeadAssignmentsWrite(
                leadIds=[lead["leadId"]],
                consultantIds=[],
            ),
            manager,
            db,
        )
    assert bulk_assignment_error.value.status_code == 409

    with pytest.raises(HTTPException) as update_error:
        update_lead(
            lead["leadId"],
            LeadWrite(
                hoTen="Changed",
                soDienThoai="0901234567",
                email="an@example.com",
                nguon="Website",
            ),
            manager,
            db,
        )
    assert update_error.value.status_code == 409


def test_lead_conversion_requires_email_and_rolls_back_on_email_failure(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    manager = add_user(db, 69, 7, "Manager")
    db.add(VaiTro(VaiTroId=2, TenVaiTro="Học viên"))
    db.commit()
    no_email = create_lead(
        LeadWrite(
            hoTen="Nguyễn An",
            soDienThoai="0901234567",
            nguon="Website",
        ),
        manager,
        db,
    )
    with pytest.raises(HTTPException) as missing_email:
        convert_lead_to_student(no_email["leadId"], manager, db)
    assert missing_email.value.status_code == 422
    assert db.query(LeadConversion).count() == 0

    email_lead = create_lead(
        LeadWrite(
            hoTen="Trần Bình",
            soDienThoai="0912345678",
            email="binh@example.com",
            nguon="Website",
        ),
        manager,
        db,
    )

    def fail_send_activation_email(**_kwargs: object) -> None:
        assert "recipient_email" in _kwargs
        raise RuntimeError("SMTP unavailable")

    monkeypatch.setattr(
        "app.routers.admissions.send_activation_email",
        fail_send_activation_email,
    )
    with pytest.raises(HTTPException) as email_error:
        convert_lead_to_student(email_lead["leadId"], manager, db)
    assert email_error.value.status_code == 502
    db.expire_all()
    persisted_lead = db.query(Lead).filter(
        Lead.LeadId == email_lead["leadId"]
    ).one()
    assert persisted_lead.TrangThai == "Mới"
    assert db.query(LeadConversion).count() == 0
    assert db.query(NguoiDung).filter(
        NguoiDung.Email == "binh@example.com"
    ).count() == 0


def test_consultants_are_listed_and_only_assigned_leads_are_visible(db: Session):
    add_program(db)
    manager = add_user(db, 70, 7, "Manager")
    consultant = add_user(db, 50, 5, "Consultant")
    other_consultant = add_user(db, 51, 5, "Other consultant")
    unassigned_consultant = add_user(db, 52, 5, "Unassigned consultant")
    lead = create_lead(
        LeadWrite(
            hoTen="Nguyễn An",
            soDienThoai="090 123 4567",
            chuongTrinhId=1,
            nguon="Website",
            ghiChu="Call after 5pm",
        ),
        manager,
        db,
    )
    assert lead["duplicatePhone"] is False
    assert lead["ghiChu"] == "Call after 5pm"
    assigned = replace_lead_assignments(
        lead["leadId"],
        LeadAssignmentsWrite(consultantIds=[consultant.NguoiDungId]),
        manager,
        db,
    )
    assert assigned["consultantIds"] == [consultant.NguoiDungId]
    history = get_lead_assignments(lead["leadId"], manager, db)
    assert len(history) == 1
    assert history[0]["dangPhanCong"] is True
    manager_payload = list_leads(None, None, None, None, None, None, manager, db)[0]
    assert manager_payload["nguoiPhuTrach"] == [
        {"nguoiDungId": consultant.NguoiDungId, "hoTen": consultant.HoTen},
    ]
    assert manager_payload["lichSuBanGiao"][0]["nguoiBanGiao"] == manager.HoTen
    assert [person["nguoiDungId"] for person in list_admissions_consultants(db)] == [
        consultant.NguoiDungId,
        other_consultant.NguoiDungId,
        unassigned_consultant.NguoiDungId,
    ]
    assert len(
        list_leads(
            None, None, None, None, None, None, consultant, db
        )
    ) == 1
    assert list_leads(None, None, None, None, None, None, other_consultant, db) == []

    with pytest.raises(ValueError, match="một tư vấn viên"):
        LeadAssignmentsWrite(
            consultantIds=[consultant.NguoiDungId, other_consultant.NguoiDungId]
        )

    replacement = replace_lead_assignments(
        lead["leadId"],
        LeadAssignmentsWrite(consultantIds=[other_consultant.NguoiDungId]),
        manager,
        db,
    )
    assert replacement["consultantIds"] == [other_consultant.NguoiDungId]
    assert list_leads(None, None, None, None, None, None, consultant, db) == []
    assert len(list_leads(None, None, None, None, None, None, other_consultant, db)) == 1
    with pytest.raises(HTTPException) as reassigned_error:
        _get_visible_lead(db, lead["leadId"], consultant)
    assert reassigned_error.value.status_code == 404

    unassigned = replace_lead_assignments(
        lead["leadId"],
        LeadAssignmentsWrite(consultantIds=[]),
        manager,
        db,
    )
    assert unassigned["consultantIds"] == []
    assert list_leads(None, None, None, None, None, None, other_consultant, db) == []
    assert unassigned["assignmentHistory"][-1]["ngayBoPhanCong"] is not None

    duplicate = create_lead(
        LeadWrite(
            hoTen="Another",
            soDienThoai="0901234567",
            chuongTrinhId=1,
            nguon="Referral",
        ),
        manager,
        db,
    )
    assert duplicate["duplicatePhone"] is True
    assert len(list_leads("Mới", "Referral", None, None, None, "Another", manager, db)) == 1

    with pytest.raises(HTTPException) as error:
        _get_visible_lead(db, lead["leadId"], unassigned_consultant)
    assert error.value.status_code == 404


def test_active_assignment_boolean_filter_is_valid_for_sql_server():
    statement = (
        LeadAssignmentHistory.__table__.select()
        .where(LeadAssignmentHistory.DangPhanCong.in_([True]))
    )
    sql = str(
        statement.compile(
            dialect=mssql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "[DangPhanCong] IN (1)" in sql
    assert "[DangPhanCong] IS 1" not in sql


def test_subject_cannot_be_archived_when_attached_to_class(db: Session):
    subject = create_subject(
        SubjectCreate(
            maMonHoc="SUB_ACTIVE",
            tenMonHoc="Môn gắn lớp",
            soBuoi=5,
        ),
        db,
    )
    program = add_program(db, 2)
    instructor = add_user(db, 88, 3, "Instructor")
    class_obj = LopHoc(
        MaLop="CLASS01",
        TenLop="Lớp Thử Nghiệm",
        ChuongTrinhId=program.ChuongTrinhId,
        GiangVienId=instructor.NguoiDungId,
        NamHoc="2025-2026",
        TrangThai="DangMo",
        NgayTao=datetime.now(),
    )
    db.add(class_obj)
    db.flush()
    db.add(
        LopHocMonHoc(
            LopHocId=class_obj.LopHocId,
            MonHocId=subject["monHocId"],
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as conflict_err:
        archive_subject(subject["monHocId"], db)
    assert conflict_err.value.status_code == 409
    assert "Môn học đã có lớp học nên không thể xóa" in conflict_err.value.detail

    # Remove from class and archive should succeed
    db.query(LopHocMonHoc).filter(
        LopHocMonHoc.MonHocId == subject["monHocId"]
    ).delete()
    db.commit()

    archive_res = archive_subject(subject["monHocId"], db)
    assert archive_res["message"] == "Đã lưu trữ môn học."
    archived_sub = db.query(MonHoc).filter(MonHoc.MonHocId == subject["monHocId"]).first()
    assert archived_sub.TrangThai == "Ngừng hoạt động"


def test_bulk_assign_leads_updates_multiple_leads_and_records_history(db: Session):
    add_program(db, 3)
    manager = add_user(db, 71, 7, "Training Manager Bulk")
    consultant_a = add_user(db, 53, 5, "Consultant A")
    consultant_b = add_user(db, 54, 5, "Consultant B")

    lead1 = create_lead(
        LeadWrite(
            hoTen="Lead 1",
            soDienThoai="0911000001",
            chuongTrinhId=3,
            nguon="Website",
        ),
        manager,
        db,
    )
    lead2 = create_lead(
        LeadWrite(
            hoTen="Lead 2",
            soDienThoai="0911000002",
            chuongTrinhId=3,
            nguon="Facebook",
        ),
        manager,
        db,
    )

    result = bulk_assign_leads(
        BulkLeadAssignmentsWrite(
            leadIds=[lead1["leadId"], lead2["leadId"]],
            consultantIds=[consultant_a.NguoiDungId],
        ),
        manager,
        db,
    )
    assert result["leadIds"] == [lead1["leadId"], lead2["leadId"]]
    assert result["consultantIds"] == [consultant_a.NguoiDungId]

    history1 = get_lead_assignments(lead1["leadId"], manager, db)
    assert len(history1) == 1
    assert {h["nguoiDungId"] for h in history1} == {consultant_a.NguoiDungId}

    history2 = get_lead_assignments(lead2["leadId"], manager, db)
    assert len(history2) == 1

    # Consultants should now see both leads
    assert len(list_leads(None, None, None, None, None, None, consultant_a, db)) == 2
    assert list_leads(None, None, None, None, None, None, consultant_b, db) == []

    cleared = bulk_assign_leads(
        BulkLeadAssignmentsWrite(
            leadIds=[lead1["leadId"], lead2["leadId"]],
            consultantIds=[],
        ),
        manager,
        db,
    )
    assert cleared["consultantIds"] == []
    assert list_leads(None, None, None, None, None, None, consultant_a, db) == []
    assert all(
        assignments[-1]["ngayBoPhanCong"] is not None
        for assignments in (
            get_lead_assignments(lead1["leadId"], manager, db),
            get_lead_assignments(lead2["leadId"], manager, db),
        )
    )

    with pytest.raises(ValueError, match="một tư vấn viên"):
        BulkLeadAssignmentsWrite(
            leadIds=[lead1["leadId"]],
            consultantIds=[consultant_a.NguoiDungId, consultant_b.NguoiDungId],
        )
