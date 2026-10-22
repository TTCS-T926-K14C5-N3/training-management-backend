from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.admissions import (
    AdmissionsLead,
    AdmissionsLeadAssignment,
    AdmissionsLeadInteraction,
    AdmissionsLeadStatusHistory,
)
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.curriculum import ProgramSession, ProgramSubject
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.quyen import Quyen
from app.models.vai_tro import VaiTro
from app.models.vai_tro_quyen import VaiTroQuyen
from app.routers.academic import (
    create_subject,
    create_training_program,
    get_program_subjects,
    update_program_sessions,
    update_program_subjects,
    clone_program_sessions,
)
from app.routers.admissions import (
    _active_assignment_filter,
    create_interaction,
    create_lead,
    create_public_lead,
    list_leads,
    update_lead_status,
)
from app.schemas.academic import SubjectCreate, TrainingProgramWrite
from app.schemas.admissions import (
    LeadInteractionWrite,
    LeadStatusWrite,
    LeadWrite,
    PublicLeadWrite,
)
from app.schemas.curriculum import (
    ProgramSessionsClone,
    ProgramSessionsWrite,
    ProgramSessionItem,
    ProgramSubjectsWrite,
    ProgramSubjectItem,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def add_user(db: Session, user_id: int, role_id: int, name: str) -> NguoiDung:
    if db.get(VaiTro, role_id) is None:
        db.add(VaiTro(VaiTroId=role_id, TenVaiTro=f"Vai trò {role_id}"))
    user = NguoiDung(
        NguoiDungId=user_id,
        HoTen=name,
        Email=f"user{user_id}@example.com",
        MatKhauHash="not-a-real-password-hash",
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


def test_program_subjects_sessions_and_clone_use_persisted_data(db: Session):
    create_subject(
        SubjectCreate(
            maMonHoc="CURR-01",
            tenMonHoc="Môn nguồn",
            soBuoi=3,
            trongSo=0.5,
            moTaChuanDauRa="Chuẩn đầu ra",
        ),
        db,
    )
    create_subject(
        SubjectCreate(
            maMonHoc="CURR-02",
            tenMonHoc="Môn đích",
            soBuoi=3,
        ),
        db,
    )
    program = create_training_program(
        TrainingProgramWrite(
            maChuongTrinh="CURR-PROG",
            tenChuongTrinh="Chương trình",
            tongThoiLuong=100,
            hocPhiChuan=0,
        ),
        db,
    )
    program_id = program["chuongTrinhId"]
    update_program_subjects(
        program_id,
        ProgramSubjectsWrite(
            subjects=[
                ProgramSubjectItem(monHocId=1, thuTu=1, monTienQuyetId=None),
                ProgramSubjectItem(monHocId=2, thuTu=2, monTienQuyetId=1),
            ]
        ),
        db,
    )
    update_program_sessions(
        program_id,
        1,
        ProgramSessionsWrite(
            sessions=[
                ProgramSessionItem(
                    soThuTu=1,
                    chuDe="Chủ đề 1",
                    mucTieu="Mục tiêu",
                )
            ]
        ),
        db,
    )
    clone_program_sessions(
        program_id,
        2,
        ProgramSessionsClone(sourceSubjectId=1),
        db,
    )

    result = get_program_subjects(program_id, db)

    assert [item["monHocId"] for item in result] == [1, 2]
    assert result[0]["trongSo"] == 0.5
    assert result[1]["monTienQuyetId"] == 1
    assert result[0]["sessions"][0]["chuDe"] == "Chủ đề 1"
    assert result[1]["sessions"][0]["mucTieu"] == "Mục tiêu"
    assert db.query(ProgramSubject).count() == 2
    assert db.query(ProgramSession).count() == 2


def test_program_subject_update_rejects_external_prerequisite(db: Session):
    create_subject(
        SubjectCreate(maMonHoc="CURR-A", tenMonHoc="Môn A"),
        db,
    )
    program = create_training_program(
        TrainingProgramWrite(
            maChuongTrinh="CURR-A-PROG",
            tenChuongTrinh="Chương trình A",
            tongThoiLuong=10,
            hocPhiChuan=0,
        ),
        db,
    )

    with pytest.raises(HTTPException) as error:
        update_program_subjects(
            program["chuongTrinhId"],
            ProgramSubjectsWrite(
                subjects=[
                    ProgramSubjectItem(
                        monHocId=1,
                        thuTu=1,
                        monTienQuyetId=99,
                    )
                ]
            ),
            db,
        )

    assert error.value.status_code == 422
    assert db.query(ProgramSubject).count() == 0


def test_public_lead_honeypot_does_not_store_lead(db: Session):
    result = create_public_lead(
        PublicLeadWrite(
            hoTen="Người dùng",
            soDienThoai="0901234567",
            email="public@example.com",
            website="bot-filled-value",
        ),
        db,
    )

    assert result["message"]
    assert db.query(AdmissionsLead).count() == 0


def test_lead_workflow_assignment_scope_history_and_interactions(db: Session):
    manager = add_user(db, 70, 7, "Quản lý tuyển sinh")
    consultant = add_user(db, 71, 5, "Tư vấn viên")
    db.add_all(
        Quyen(MaQuyen=code, TenQuyen=code, MoTa=code)
        for code in ("LEAD_VIEW", "LEAD_CREATE", "LEAD_UPDATE", "LEAD_ASSIGN")
    )
    db.flush()
    for permission in db.query(Quyen).all():
        db.add(VaiTroQuyen(VaiTroId=5, QuyenId=permission.QuyenId))
    db.commit()

    lead = create_lead(
        LeadWrite(
            hoTen="Học viên tiềm năng",
            soDienThoai="0901234567",
            email="lead@example.com",
            nguon="Website",
        ),
        current_user=manager,
        db=db,
    )
    lead_id = lead["leadId"]

    from app.routers.admissions import assign_lead
    from app.schemas.admissions import LeadAssignmentWrite

    assign_lead(
        lead_id,
        LeadAssignmentWrite(consultantIds=[consultant.NguoiDungId]),
        current_user=manager,
        db=db,
    )
    update_lead_status(
        lead_id,
        LeadStatusWrite(trangThai="Đã liên hệ"),
        current_user=consultant,
        db=db,
    )
    create_interaction(
        lead_id,
        LeadInteractionWrite(
            loai="Gọi",
            noiDung="Đã trao đổi thông tin",
            thoiDiem=datetime.now(),
            henGoiLaiLuc=datetime.now() + timedelta(days=1),
        ),
        current_user=consultant,
        db=db,
    )

    visible = list_leads(
        search="tiềm năng",
        lead_status="Đã liên hệ",
        source="Website",
        assigned_user_id=consultant.NguoiDungId,
        unassigned=False,
        start_date=None,
        end_date=None,
        current_user=consultant,
        db=db,
    )

    assert len(visible) == 1
    assert visible[0]["nguoiPhuTrach"][0]["nguoiDungId"] == consultant.NguoiDungId
    assert visible[0]["lichSuTrangThai"][0]["trangThaiMoi"] == "Đã liên hệ"
    assert visible[0]["tuongTacs"][0]["noiDung"] == "Đã trao đổi thông tin"
    assert db.query(AdmissionsLeadStatusHistory).count() == 2
    assert db.query(AdmissionsLeadInteraction).count() == 1


def test_active_assignment_filter_compiles_for_sql_server():
    statement = select(AdmissionsLeadAssignment).where(
        _active_assignment_filter()
    )
    compiled = str(statement.compile(dialect=mssql.dialect()))

    assert "[DangPhanCong] = 1" in compiled
    assert "IS 1" not in compiled


def test_admissions_non_manager_cannot_access_unassigned_lead(db: Session):
    consultant = add_user(db, 71, 5, "Tư vấn viên")
    db.add(Quyen(MaQuyen="LEAD_UPDATE", TenQuyen="Sửa lead", MoTa=""))
    db.flush()
    permission = db.query(Quyen).filter(Quyen.MaQuyen == "LEAD_UPDATE").one()
    db.add(VaiTroQuyen(VaiTroId=5, QuyenId=permission.QuyenId))
    lead = AdmissionsLead(
        HoTen="Chưa phân công",
        SoDienThoai="0901234567",
        Nguon="Website",
        TrangThai="Mới",
        NgayTao=datetime.now(),
        NgayCapNhat=datetime.now(),
    )
    db.add(lead)
    db.commit()

    with pytest.raises(HTTPException) as error:
        update_lead_status(
            lead.LeadId,
            LeadStatusWrite(trangThai="Đã liên hệ"),
            current_user=consultant,
            db=db,
        )

    assert error.value.status_code == 403
    assert lead.TrangThai == "Mới"
