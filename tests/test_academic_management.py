from datetime import datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.diem import Diem
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.mon_hoc import MonHoc
from app.models.vai_tro import VaiTro
from app.routers.academic import (
    _class_payload,
    archive_class,
    create_class,
    create_grade,
    create_subject,
    create_training_program,
    delete_training_program,
    delete_grade,
    get_class_options,
    list_grades,
    update_class,
    update_grade,
    update_training_program,
)
from app.schemas.academic import (
    ClassWrite,
    GradeWrite,
    SubjectCreate,
    TrainingProgramWrite,
)
from app.services.academic_service import (
    accessible_classes,
    can_access_class,
    ensure_valid_academic_year,
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
    if db.query(VaiTro).filter(VaiTro.VaiTroId == role_id).first() is None:
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


def setup_academic_class(db: Session, teacher_id: int = 3):
    teacher = add_user(db, teacher_id, 3, f"Giảng viên {teacher_id}")
    student = add_user(db, 20, 2, "Học viên Một")
    second_student = add_user(db, 21, 2, "Học viên Hai")
    subject = create_subject(
        SubjectCreate(
            maMonHoc="CS101",
            tenMonHoc="Lập trình",
            soTinChi=3,
        ),
        db,
    )
    lop_hoc = create_class(
        ClassWrite(
            maLop=f"CLASS{teacher_id}",
            tenLop="Lớp kiểm thử",
            namHoc="2025-2026",
            giangVienId=teacher_id,
            hocVienIds=[20, 21],
            monHocIds=[subject["monHocId"]],
        ),
        db,
    )
    return teacher, student, second_student, subject, lop_hoc


def test_class_visibility_is_scoped_to_roles(db: Session):
    teacher, student, _second_student, _subject, lop_hoc = setup_academic_class(db)
    manager = add_user(db, 7, 7, "Quản lý đào tạo")
    other_teacher = add_user(db, 4, 3, "Giảng viên khác")

    assert [item.LopHocId for item in accessible_classes(db, teacher)] == [
        lop_hoc["lopHocId"]
    ]
    assert accessible_classes(db, other_teacher) == []
    assert [item.LopHocId for item in accessible_classes(db, student)] == [
        lop_hoc["lopHocId"]
    ]
    assert [item.LopHocId for item in accessible_classes(db, manager)] == [
        lop_hoc["lopHocId"]
    ]


def test_legacy_named_admin_can_see_and_access_all_classes(db: Session):
    _teacher, _student, _second_student, _subject, record = setup_academic_class(
        db,
        teacher_id=30,
    )
    legacy_admin = add_user(db, 1, 1, "Quản trị cũ")
    db.query(VaiTro).filter(VaiTro.VaiTroId == 1).one().TenVaiTro = (
        "Quản trị hệ thống"
    )
    db.commit()

    lop_hoc = db.query(LopHoc).filter(
        LopHoc.LopHocId == record["lopHocId"]
    ).one()

    assert [item.LopHocId for item in accessible_classes(db, legacy_admin)] == [
        lop_hoc.LopHocId
    ]
    assert can_access_class(db, legacy_admin, lop_hoc) is True


def test_instructor_can_enter_assigned_class_grades_and_student_sees_own_only(
    db: Session,
):
    teacher, student, second_student, subject, lop_hoc = setup_academic_class(db)
    grade_request = GradeWrite(
        lopHocId=lop_hoc["lopHocId"],
        hocVienId=student.NguoiDungId,
        monHocId=subject["monHocId"],
        hocKy=1,
        namHoc="2025-2026",
        diemQuaTrinh=8,
        diemGiuaKy=7.5,
        diemCuoiKy=9,
    )
    create_grade(grade_request, teacher, db)
    create_grade(
        grade_request.model_copy(update={"hoc_vien_id": second_student.NguoiDungId}),
        teacher,
        db,
    )

    visible_to_student = list_grades(
        lop_hoc_id=None,
        mon_hoc_id=None,
        hoc_ky=None,
        nam_hoc=None,
        current_user=student,
        db=db,
    )
    visible_to_teacher = list_grades(
        lop_hoc_id=None,
        mon_hoc_id=None,
        hoc_ky=None,
        nam_hoc=None,
        current_user=teacher,
        db=db,
    )

    assert len(visible_to_student) == 1
    assert visible_to_student[0]["hocVienId"] == student.NguoiDungId
    assert len(visible_to_teacher) == 2


def test_instructor_cannot_write_grade_for_unassigned_class(db: Session):
    teacher, student, _second_student, subject, lop_hoc = setup_academic_class(db)
    other_teacher = add_user(db, 4, 3, "Giảng viên khác")
    request = GradeWrite(
        lopHocId=lop_hoc["lopHocId"],
        hocVienId=student.NguoiDungId,
        monHocId=subject["monHocId"],
        hocKy=1,
        namHoc="2025-2026",
        diemQuaTrinh=8,
    )

    with pytest.raises(HTTPException) as error:
        create_grade(request, other_teacher, db)

    assert error.value.status_code == 403
    assert "không được phân công" in error.value.detail
    assert db.query(Diem).count() == 0


def test_grade_rejects_students_or_subjects_not_assigned_to_class(db: Session):
    teacher, _student, _second_student, subject, lop_hoc = setup_academic_class(db)
    unassigned_student = add_user(db, 22, 2, "Học viên chưa ghi danh")
    request = GradeWrite(
        lopHocId=lop_hoc["lopHocId"],
        hocVienId=unassigned_student.NguoiDungId,
        monHocId=subject["monHocId"],
        hocKy=1,
        namHoc="2025-2026",
        diemQuaTrinh=8,
    )

    with pytest.raises(HTTPException) as error:
        create_grade(request, teacher, db)

    assert error.value.status_code == 422
    assert "chưa được ghi danh" in error.value.detail


def test_class_update_and_archive_keep_class_history(db: Session):
    _teacher, _student, _second_student, subject, record = setup_academic_class(db)
    manager = add_user(db, 7, 7, "Quản lý đào tạo")
    update_request = ClassWrite(
        maLop=record["maLop"],
        tenLop="Lớp đã cập nhật",
        namHoc="2025-2026",
        giangVienId=3,
        hocVienIds=[20, 21],
        monHocIds=[subject["monHocId"]],
    )

    updated = update_class(
        record["lopHocId"],
        update_request,
        current_user=manager,
        db=db,
    )
    archive_class(
        record["lopHocId"],
        current_user=manager,
        db=db,
    )

    assert updated["tenLop"] == "Lớp đã cập nhật"
    archived = db.query(LopHoc).filter(
        LopHoc.LopHocId == record["lopHocId"]
    ).one()
    assert archived.TrangThai == "Ngừng hoạt động"


def test_classes_with_locked_instructors_are_flagged_for_handover(db: Session):
    teacher, _student, _second_student, _subject, record = setup_academic_class(db)
    teacher.TrangThai = "BiKhoa"
    db.commit()

    lop_hoc = db.query(LopHoc).filter(
        LopHoc.LopHocId == record["lopHocId"]
    ).one()

    assert _class_payload(db, lop_hoc)["canBanGiao"] is True


def test_class_options_list_active_users_by_assigned_role(db: Session):
    teacher = add_user(db, 50, 3, "Giảng viên đang hoạt động")
    student = add_user(db, 51, 2, "Học viên đang hoạt động")
    locked_teacher = add_user(db, 52, 3, "Giảng viên đã khóa")
    locked_teacher.TrangThai = "BiKhoa"
    create_subject(
        SubjectCreate(
            maMonHoc="OPTIONS-01",
            tenMonHoc="Môn học đang hoạt động",
            soTinChi=3,
        ),
        db,
    )
    inactive_subject = create_subject(
        SubjectCreate(
            maMonHoc="OPTIONS-02",
            tenMonHoc="Môn học sẽ ngừng",
            soTinChi=2,
        ),
        db,
    )
    db.query(MonHoc).filter(
        MonHoc.MonHocId == inactive_subject["monHocId"]
    ).one().TrangThai = "Ngừng hoạt động"
    db.commit()

    options = get_class_options(db=db)

    assert [item["nguoiDungId"] for item in options["giangViens"]] == [
        teacher.NguoiDungId
    ]
    assert [item["nguoiDungId"] for item in options["hocViens"]] == [
        student.NguoiDungId
    ]
    assert [item["tenMonHoc"] for item in options["monHocs"]] == [
        "Môn học đang hoạt động"
    ]


def test_training_program_code_must_be_unique(db: Session):
    request = TrainingProgramWrite(
        maChuongTrinh="PROG-01",
        tenChuongTrinh="Chương trình kiểm thử",
        tongThoiLuong=120,
        hocPhiChuan=1500000,
    )
    create_training_program(request, db)

    with pytest.raises(HTTPException) as error:
        create_training_program(request, db)

    assert error.value.status_code == 409
    assert db.query(ChuongTrinhDaoTao).count() == 1


def test_class_uses_program_and_linked_program_cannot_be_deleted(db: Session):
    program = create_training_program(
        TrainingProgramWrite(
            maChuongTrinh="PROG-02",
            tenChuongTrinh="Lập trình Python",
            moTa="Chương trình nền tảng",
            tongThoiLuong=80,
            hocPhiChuan=2500000,
        ),
        db,
    )

    result = create_class(
        ClassWrite(
            maLop="PY-2026",
            tenLop="Tên gửi từ client",
            namHoc="2026-2027",
            chuongTrinhId=program["chuongTrinhId"],
            giangVienId=None,
            hocVienIds=[],
            monHocIds=[],
        ),
        db,
    )

    assert result["tenLop"] == "Lập trình Python"
    assert result["chuongTrinhId"] == program["chuongTrinhId"]
    with pytest.raises(HTTPException) as error:
        delete_training_program(program["chuongTrinhId"], db)
    assert error.value.status_code == 409


def test_program_with_active_class_can_be_discontinued_but_not_deleted(
    db: Session,
):
    program = create_training_program(
        TrainingProgramWrite(
            maChuongTrinh="PROG-04",
            tenChuongTrinh="Chương trình đang chạy",
            tongThoiLuong=40,
            hocPhiChuan=900000,
        ),
        db,
    )
    create_class(
        ClassWrite(
            maLop="RUNNING-01",
            tenLop="Tên lớp",
            namHoc="2026-2027",
            chuongTrinhId=program["chuongTrinhId"],
            hocVienIds=[],
            monHocIds=[],
        ),
        db,
    )
    stopped_program = update_training_program(
        program["chuongTrinhId"],
        TrainingProgramWrite(
            maChuongTrinh="PROG-04",
            tenChuongTrinh="Chương trình đang chạy",
            tongThoiLuong=40,
            hocPhiChuan=900000,
            trangThai="Ngừng áp dụng",
        ),
        db,
    )

    assert stopped_program["trangThai"] == "Ngừng áp dụng"
    assert stopped_program["soLop"] == 1
    with pytest.raises(HTTPException) as error:
        delete_training_program(program["chuongTrinhId"], db)
    assert error.value.status_code == 409


def test_stopped_program_cannot_be_used_to_open_new_class(db: Session):
    program = ChuongTrinhDaoTao(
        MaChuongTrinh="PROG-03",
        TenChuongTrinh="Chương trình ngừng",
        TongThoiLuong=60,
        HocPhiChuan=0,
        TrangThai="Ngừng áp dụng",
        NgayTao=datetime.now(),
    )
    db.add(program)
    db.commit()

    with pytest.raises(HTTPException) as error:
        create_class(
            ClassWrite(
                maLop="STOPPED-01",
                tenLop="Không được tạo",
                namHoc="2026-2027",
                chuongTrinhId=program.ChuongTrinhId,
                hocVienIds=[],
                monHocIds=[],
            ),
            db,
        )
    assert error.value.status_code == 422
    assert db.query(LopHoc).count() == 0


def test_grade_update_and_delete_are_supported(db: Session):
    teacher, student, _second_student, subject, lop_hoc = setup_academic_class(db)
    request = GradeWrite(
        lopHocId=lop_hoc["lopHocId"],
        hocVienId=student.NguoiDungId,
        monHocId=subject["monHocId"],
        hocKy=1,
        namHoc="2025-2026",
        diemQuaTrinh=8,
        diemGiuaKy=7,
        diemCuoiKy=9,
    )
    created = create_grade(request, teacher, db)
    updated = update_grade(
        created["diemId"],
        request.model_copy(update={"diem_giua_ky": 8.25}),
        current_user=teacher,
        db=db,
    )
    administrator = add_user(db, 8, 8, "Quản trị hệ thống")
    delete_grade(
        created["diemId"],
        current_user=administrator,
        db=db,
    )

    assert updated["diemGiuaKy"] == 8.25
    assert db.query(Diem).filter(Diem.DiemId == created["diemId"]).count() == 0


def test_instructor_cannot_update_grade_from_an_unassigned_class(db: Session):
    teacher, student, _second_student, subject, first_class = setup_academic_class(db)
    grade = create_grade(
        GradeWrite(
            lopHocId=first_class["lopHocId"],
            hocVienId=student.NguoiDungId,
            monHocId=subject["monHocId"],
            hocKy=1,
            namHoc="2025-2026",
            diemQuaTrinh=8,
        ),
        teacher,
        db,
    )
    other_teacher = add_user(db, 4, 3, "Giảng viên khác")
    other_student = add_user(db, 22, 2, "Học viên lớp khác")
    other_subject = create_subject(
        SubjectCreate(
            maMonHoc="CS102",
            tenMonHoc="Cấu trúc dữ liệu",
        ),
        db,
    )
    second_class = create_class(
        ClassWrite(
            maLop="CLASS-OTHER",
            tenLop="Lớp khác",
            namHoc="2025-2026",
            giangVienId=other_teacher.NguoiDungId,
            hocVienIds=[other_student.NguoiDungId],
            monHocIds=[other_subject["monHocId"]],
        ),
        db,
    )
    request = GradeWrite(
        lopHocId=second_class["lopHocId"],
        hocVienId=other_student.NguoiDungId,
        monHocId=other_subject["monHocId"],
        hocKy=1,
        namHoc="2025-2026",
        diemQuaTrinh=6,
    )

    with pytest.raises(HTTPException) as error:
        update_grade(
            grade["diemId"],
            request,
            current_user=other_teacher,
            db=db,
        )

    assert error.value.status_code == 403
    assert db.query(Diem).filter(Diem.DiemId == grade["diemId"]).one().LopHocId == (
        first_class["lopHocId"]
    )


@pytest.mark.parametrize(
    "academic_year",
    ["2025", "2025-2027", "abc-2026", "2025-26"],
)
def test_academic_year_must_be_two_consecutive_years(academic_year: str):
    with pytest.raises(ValueError):
        ensure_valid_academic_year(academic_year)


def test_grade_model_has_score_range_and_unique_term_constraints():
    constraints = {constraint.name for constraint in Diem.__table__.constraints}

    assert "UQ_Diem_HocVien_Lop_Mon_HocKy_NamHoc" in constraints
    assert {
        "CK_Diem_DiemQuaTrinh",
        "CK_Diem_DiemGiuaKy",
        "CK_Diem_DiemCuoiKy",
        "CK_Diem_HocKy",
    } <= constraints


def test_class_and_grade_link_models_use_existing_users():
    assert LopHoc.__table__.c.GiangVienId.foreign_keys
    assert LopHocHocVien.__table__.c.HocVienId.foreign_keys
    assert LopHocMonHoc.__table__.c.MonHocId.foreign_keys


def test_grade_schema_enforces_score_range_and_precision():
    with pytest.raises(ValidationError):
        GradeWrite(
            lopHocId=1,
            hocVienId=2,
            monHocId=3,
            hocKy=1,
            namHoc="2025-2026",
            diemQuaTrinh=10.01,
        )

    with pytest.raises(ValidationError):
        GradeWrite(
            lopHocId=1,
            hocVienId=2,
            monHocId=3,
            hocKy=1,
            namHoc="2025-2026",
            diemQuaTrinh=7.123,
        )


def test_academic_routes_are_registered_in_the_fastapi_app():
    from app.main import app

    paths = set(app.openapi()["paths"])

    assert "/academic/classes" in paths
    assert "/academic/programs" in paths
    assert "/academic/programs/{program_id}" in paths
    assert "/academic/grades" in paths
    assert "/academic/subjects" in paths
