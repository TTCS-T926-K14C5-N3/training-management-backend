from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.database import Base
from app.models.admissions import Lead
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.mon_hoc import MonHoc
from app.models.vai_tro import VaiTro
from app.routers.academic import (
    archive_subject,
    create_subject,
    get_program_subject_sessions,
    get_program_subjects,
    replace_program_subject_sessions,
    replace_program_subjects,
)
from app.routers.admissions import (
    _public_submissions,
    create_lead,
    get_lead_assignments,
    list_admissions_consultants,
    list_leads,
    replace_lead_assignments,
    submit_public_lead,
)
from app.schemas.academic import SubjectCreate
from app.schemas.admissions import (
    LeadAssignmentsWrite,
    LeadWrite,
    PublicLeadCreate,
)
from app.schemas.curriculum import ProgramSubjectsWrite, SessionsWrite
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
    assert db.query(MonHoc).filter_by(
        MonHocId=first["monHocId"]
    ).one().TrongSo == 0.4
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
        LeadAssignmentsWrite(
            consultantIds=[consultant.NguoiDungId, other_consultant.NguoiDungId]
        ),
        manager,
        db,
    )
    assert assigned["consultantIds"] == [
        consultant.NguoiDungId,
        other_consultant.NguoiDungId,
    ]
    history = get_lead_assignments(lead["leadId"], manager, db)
    assert len(history) == 2
    assert history[0]["dangPhanCong"] is True
    manager_payload = list_leads(None, None, None, None, None, None, manager, db)[0]
    assert manager_payload["nguoiPhuTrach"] == [
        {"nguoiDungId": consultant.NguoiDungId, "hoTen": consultant.HoTen},
        {"nguoiDungId": other_consultant.NguoiDungId, "hoTen": other_consultant.HoTen},
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
    assert len(list_leads(None, None, None, None, None, None, other_consultant, db)) == 1

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
        from app.routers.admissions import _get_visible_lead
        _get_visible_lead(db, lead["leadId"], unassigned_consultant)
    assert error.value.status_code == 404
