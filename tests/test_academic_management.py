from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.attendance import AbsenceThreshold, AttendanceRecord
from app.models.diem import Diem
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.mon_hoc import MonHoc
from app.models.phong_hoc import PhongHoc
from app.models.student_enrollment_action import StudentEnrollmentAction
from app.models.tuyen_sinh_lead_chuyen_doi import TuyenSinhLeadChuyenDoi
from app.models.vai_tro import VaiTro
from app.routers.academic import (
    _class_payload,
    archive_class,
    create_class,
    create_grade,
    create_room,
    create_student_enrollment_action,
    create_subject,
    create_training_program,
    delete_training_program,
    delete_grade,
    get_student_academic_profile,
    get_student_profile,
    get_class_options,
    list_rooms,
    enroll_students_in_class,
    list_grades,
    list_student_statuses,
    update_class,
    update_grade,
    update_student_profile,
    update_training_program,
    router,
)
from app.schemas.academic import (
    ClassInstructorAssignment,
    ClassEnrollmentsWrite,
    ClassStudentActionWrite,
    ClassWrite,
    GradeWrite,
    StudentProfileUpdate,
    SubjectCreate,
    TrainingProgramWrite,
    RoomCreate,
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


def test_admin_role_name_grants_schedule_scope_when_role_id_differs(db: Session):
    teacher, student, _second_student, subject, class_data = setup_academic_class(db)
    administrator = add_user(db, 70, 1, "Administrator")
    create_grade(
        GradeWrite(
            lopHocId=class_data["lopHocId"],
            hocVienId=student.NguoiDungId,
            monHocId=subject["monHocId"],
            hocKy=1,
            namHoc="2025-2026",
            diemQuaTrinh=8,
        ),
        teacher,
        db,
    )
    db.query(VaiTro).filter(VaiTro.VaiTroId == 1).update(
        {VaiTro.TenVaiTro: "admin"}
    )
    db.commit()
    class_record = db.get(LopHoc, class_data["lopHocId"])

    assert [item.LopHocId for item in accessible_classes(db, administrator)] == [
        class_record.LopHocId
    ]
    assert can_access_class(db, administrator, class_record)
    assert len(
        list_grades(
            lop_hoc_id=None,
            mon_hoc_id=None,
            hoc_ky=None,
            nam_hoc=None,
            current_user=administrator,
            db=db,
        )
    ) == 1


def test_teaching_assistant_sees_only_assigned_classes(db: Session):
    _teacher, _student, _second_student, subject, class_data = setup_academic_class(db)
    assistant = add_user(db, 22, 4, "Trợ giảng")
    class_record = db.get(LopHoc, class_data["lopHocId"])
    other_class = LopHoc(
        MaLop="CLASS-OTHER",
        TenLop="Lớp khác",
        NamHoc="2025-2026",
        NgayKhaiGiang=datetime.now().date(),
        NgayTao=datetime.now(),
    )
    db.add(other_class)
    db.flush()
    db.add(
        LopHocMonHoc(
            LopHocId=other_class.LopHocId,
            MonHocId=subject["monHocId"],
        )
    )
    db.add(
        LopHocMonHocGiangVien(
            LopHocId=class_record.LopHocId,
            MonHocId=subject["monHocId"],
            GiangVienId=assistant.NguoiDungId,
            VaiTro="Trợ giảng",
        )
    )
    db.commit()

    assert [
        item.LopHocId for item in accessible_classes(db, assistant)
    ] == [class_record.LopHocId]
    assert can_access_class(db, assistant, class_record)
    assert not can_access_class(db, assistant, other_class)


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


@pytest.mark.parametrize(
    "class_status",
    ["Chuẩn bị", "Đang hoạt động", "Đang học"],
)
def test_grade_can_be_entered_for_active_class_statuses(
    db: Session,
    class_status: str,
):
    teacher, student, _second_student, subject, class_data = setup_academic_class(db)
    db.query(LopHoc).filter(
        LopHoc.LopHocId == class_data["lopHocId"]
    ).update({LopHoc.TrangThai: class_status})
    db.commit()

    grade = create_grade(
        GradeWrite(
            lopHocId=class_data["lopHocId"],
            hocVienId=student.NguoiDungId,
            monHocId=subject["monHocId"],
            hocKy=1,
            namHoc="2026-2027",
            diemQuaTrinh=10,
            diemGiuaKy=8.9,
            diemCuoiKy=8.9,
        ),
        current_user=teacher,
        db=db,
    )

    assert grade["diemQuaTrinh"] == 10
    assert db.query(Diem).count() == 1


def test_grade_cannot_be_entered_for_archived_class(db: Session):
    teacher, student, _second_student, subject, class_data = setup_academic_class(db)
    db.query(LopHoc).filter(
        LopHoc.LopHocId == class_data["lopHocId"]
    ).update({LopHoc.TrangThai: "Ngừng hoạt động"})
    db.commit()

    with pytest.raises(HTTPException) as error:
        create_grade(
            GradeWrite(
                lopHocId=class_data["lopHocId"],
                hocVienId=student.NguoiDungId,
                monHocId=subject["monHocId"],
                hocKy=1,
                namHoc="2026-2027",
                diemQuaTrinh=10,
            ),
            current_user=teacher,
            db=db,
        )

    assert error.value.status_code == 409
    assert error.value.detail == "Không thể nhập điểm cho lớp đã ngừng hoạt động."
    assert db.query(Diem).count() == 0


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


def test_preparatory_class_can_be_updated(db: Session):
    teacher, _student, _second_student, subject, record = setup_academic_class(db)
    manager = add_user(db, 7, 7, "Quản lý đào tạo")
    class_record = db.get(LopHoc, record["lopHocId"])
    class_record.TrangThai = "Chuẩn bị"
    db.commit()

    updated = update_class(
        record["lopHocId"],
        ClassWrite(
            maLop=record["maLop"],
            tenLop="Lớp chuẩn bị đã cập nhật",
            namHoc="2025-2026",
            giangVienId=teacher.NguoiDungId,
            hocVienIds=[20, 21],
            monHocIds=[subject["monHocId"]],
        ),
        current_user=manager,
        db=db,
    )

    assert updated["tenLop"] == "Lớp chuẩn bị đã cập nhật"
    assert db.get(LopHoc, record["lopHocId"]).TrangThai == "Chuẩn bị"


def test_class_instructor_assignment_accepts_frontend_camel_case_payload():
    assignment = ClassInstructorAssignment.model_validate(
        {
            "monHocId": 2,
            "giangVienId": 14,
            "vaiTro": "Chính",
        }
    )

    assert assignment.mon_hoc_id == 2
    assert assignment.giang_vien_id == 14
    assert assignment.vai_tro == "Chính"


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
    active_room = create_room(
        RoomCreate(maPhong="A-101", tenPhong="Phòng A101", sucChua=30),
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
    assert options["phongHocs"] == [active_room]


def test_rooms_can_be_listed_and_duplicate_room_codes_are_rejected(db: Session):
    room = create_room(
        RoomCreate(maPhong="B-201", tenPhong="Phòng B201", sucChua=25),
        db,
    )

    assert list_rooms(db=db) == [room]
    with pytest.raises(HTTPException) as error:
        create_room(
            RoomCreate(maPhong="B-201", tenPhong="Phòng trùng", sucChua=20),
            db,
        )
    assert error.value.status_code == 409
    assert db.query(PhongHoc).count() == 1


def test_bulk_enrollment_skips_existing_students_and_respects_capacity(
    db: Session,
):
    _teacher, _student, _second_student, _subject, class_data = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    new_student = add_user(db, 22, 2, "Học viên mới")
    class_record = db.get(LopHoc, class_data["lopHocId"])

    response = enroll_students_in_class(
        class_id=class_record.LopHocId,
        request=ClassEnrollmentsWrite(hocVienIds=[20, new_student.NguoiDungId]),
        current_user=manager,
        db=db,
    )

    assert response == {
        "daGhiDanh": [new_student.NguoiDungId],
        "siSoHienTai": 3,
        "siSoToiDa": class_record.SiSoToiDa,
    }
    assert (
        db.query(LopHocHocVien)
        .filter(LopHocHocVien.LopHocId == class_record.LopHocId)
        .count()
        == 3
    )

    class_record.SiSoToiDa = 3
    overflow_student = add_user(db, 23, 2, "Học viên vượt sĩ số")
    with pytest.raises(HTTPException) as error:
        enroll_students_in_class(
            class_id=class_record.LopHocId,
            request=ClassEnrollmentsWrite(hocVienIds=[overflow_student.NguoiDungId]),
            current_user=manager,
            db=db,
        )
    assert error.value.status_code == 409
    assert db.query(LopHocHocVien).count() == 3


def test_bulk_enrollment_rejects_duplicate_student_ids(db: Session):
    _teacher, _student, _second_student, _subject, class_data = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")

    with pytest.raises(HTTPException) as error:
        enroll_students_in_class(
            class_id=class_data["lopHocId"],
            request=ClassEnrollmentsWrite(hocVienIds=[20, 20]),
            current_user=manager,
            db=db,
        )
    assert error.value.status_code == 422


def test_bulk_enrollment_rejects_nonexistent_student_without_partial_write(
    db: Session,
):
    _teacher, _student, _second_student, _subject, class_data = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    before = db.query(LopHocHocVien).count()

    with pytest.raises(HTTPException) as error:
        enroll_students_in_class(
            class_id=class_data["lopHocId"],
            request=ClassEnrollmentsWrite(hocVienIds=[999]),
            current_user=manager,
            db=db,
        )

    assert error.value.status_code == 422
    assert db.query(LopHocHocVien).count() == before


def test_bulk_enrollment_rolls_back_all_rows_when_commit_fails(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    _teacher, _student, _second_student, _subject, class_data = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    first_new_student = add_user(db, 22, 2, "Học viên mới một")
    second_new_student = add_user(db, 23, 2, "Học viên mới hai")
    before = db.query(LopHocHocVien).count()

    def fail_commit():
        raise IntegrityError(
            "insert enrollment",
            {},
            RuntimeError("simulated SQL Server constraint failure"),
        )

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(HTTPException) as error:
        enroll_students_in_class(
            class_id=class_data["lopHocId"],
            request=ClassEnrollmentsWrite(
                hocVienIds=[first_new_student.NguoiDungId, second_new_student.NguoiDungId]
            ),
            current_user=manager,
            db=db,
        )

    assert error.value.status_code == 409
    assert db.query(LopHocHocVien).count() == before


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


def test_student_statuses_search_filter_and_pagination(db: Session):
    _teacher, student, _second_student, _subject, class_data = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    db.add(
        TuyenSinhLeadChuyenDoi(
            LeadId=1,
            NguoiDungId=student.NguoiDungId,
            MaHocVien="HV000020",
            NgayNhapHoc=datetime.now(),
            NguoiChuyenDoiId=manager.NguoiDungId,
        )
    )
    db.commit()

    result = list_student_statuses(
        search="hv000020",
        class_id=class_data["lopHocId"],
        enrollment_status="Đang học",
        has_history=False,
        status_filter=None,
        page=1,
        limit=1,
        current_user=manager,
        db=db,
    )

    assert result["total"] == 1
    assert result["pagination"] == {"page": 1, "limit": 1, "total": 1}
    assert result["items"][0]["nguoiDungId"] == student.NguoiDungId
    assert result["classes"][0]["lopHocId"] == class_data["lopHocId"]


def test_student_class_history_includes_all_class_enrollments(
    db: Session,
):
    _teacher, student, second_student, _subject, class_data = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    unenrolled_student = add_user(db, 22, 2, "Học viên chưa ghi danh")
    class_id = class_data["lopHocId"]
    db.add(
        StudentEnrollmentAction(
            HocVienId=student.NguoiDungId,
            LopHocId=class_id,
            LopHocDichId=None,
            LoaiThaoTac="BaoLuu",
            NgayHieuLuc=date.today() - timedelta(days=2),
            LyDo="Tạm dừng học",
            NguoiThucHienId=manager.NguoiDungId,
            NgayTao=datetime.now(),
        )
    )
    db.commit()

    result = list_student_statuses(
        search=None,
        class_id=None,
        enrollment_status=None,
        has_history=True,
        status_filter="HoatDong",
        page=1,
        limit=10,
        current_user=manager,
        db=db,
    )

    result_by_student = {
        item["nguoiDungId"]: item for item in result["items"]
    }
    assert result["total"] == 2
    assert student.NguoiDungId in result_by_student
    assert second_student.NguoiDungId in result_by_student
    assert unenrolled_student.NguoiDungId not in {
        item["nguoiDungId"] for item in result["items"]
    }
    assert result_by_student[student.NguoiDungId]["lopHocs"][0]["trangThai"] == "Bảo lưu"
    assert result_by_student[second_student.NguoiDungId]["lopHocs"][0]["trangThai"] == "Đang học"


def test_student_profile_returns_real_enrollment_history_and_updates(db: Session):
    _teacher, student, _second_student, _subject, _class_data = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    student.TrinhDoDauVao = "B1"
    student.GhiChuHoSo = "Ghi chú hồ sơ"
    db.commit()

    profile = get_student_profile(
        student.NguoiDungId,
        current_user=manager,
        db=db,
    )
    updated = update_student_profile(
        student.NguoiDungId,
        StudentProfileUpdate(
            hoTen="Học viên đã cập nhật",
            email=student.Email,
            soDienThoai=None,
            ngaySinh=None,
            diaChi=None,
            trinhDoDauVao="B2",
            ghiChu="Đã cập nhật",
        ),
        current_user=manager,
        db=db,
    )

    assert profile["hocVien"]["trinhDoDauVao"] == "B1"
    assert profile["hocVien"]["ghiChu"] == "Ghi chú hồ sơ"
    assert len(profile["lopHocs"]) == 1
    assert updated["message"] == "Đã cập nhật hồ sơ học viên."
    assert db.get(NguoiDung, student.NguoiDungId).TrinhDoDauVao == "B2"


def test_class_roster_and_student_profile_show_absence_threshold_flags(db: Session):
    teacher, student, _second_student, _subject, class_data = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    program = ChuongTrinhDaoTao(
        ChuongTrinhId=40,
        MaChuongTrinh="PRG-40",
        TenChuongTrinh="Chương trình kiểm thử",
        TongThoiLuong=20,
        HocPhiChuan=0,
        NgayTao=datetime.now(),
    )
    db.add(program)
    db.flush()
    class_record = db.get(LopHoc, class_data["lopHocId"])
    class_record.ChuongTrinhId = program.ChuongTrinhId
    db.add(
        AbsenceThreshold(
            ChuongTrinhId=program.ChuongTrinhId,
            TiLeToiDa=20,
            NgayCapNhat=datetime.now(),
        )
    )
    db.add_all(
        [
            AttendanceRecord(
                LopHocId=class_record.LopHocId,
                HocVienId=student.NguoiDungId,
                NgayHoc=date.today() - timedelta(days=2),
                TrangThai="unexcused_absence",
                NguoiCapNhatId=teacher.NguoiDungId,
                NgayCapNhat=datetime.now(),
            ),
            AttendanceRecord(
                LopHocId=class_record.LopHocId,
                HocVienId=student.NguoiDungId,
                NgayHoc=date.today() - timedelta(days=1),
                TrangThai="present",
                NguoiCapNhatId=teacher.NguoiDungId,
                NgayCapNhat=datetime.now(),
            ),
        ]
    )
    db.commit()

    class_payload = _class_payload(db, class_record)
    flagged_roster_student = next(
        item
        for item in class_payload["hocViens"]
        if item["nguoiDungId"] == student.NguoiDungId
    )
    profile = get_student_profile(
        student.NguoiDungId,
        current_user=manager,
        db=db,
    )

    assert flagged_roster_student["canhBaoVang"] is True
    assert flagged_roster_student["tiLeVang"] == 50
    assert flagged_roster_student["nguongVang"] == 20
    assert profile["canhBaoVangs"] == [
        {
            "programId": program.ChuongTrinhId,
            "programCode": program.MaChuongTrinh,
            "programName": program.TenChuongTrinh,
            "soBuoiVang": 1,
            "tongBuoiDiemDanh": 2,
            "tiLeVang": 50,
            "nguongVang": 20,
        }
    ]


def test_student_status_api_requires_user_view_permission(db: Session):
    teacher, _student, _second_student, _subject, _class_data = setup_academic_class(db)

    with pytest.raises(HTTPException) as error:
        list_student_statuses(
            search=None,
            class_id=None,
            enrollment_status=None,
            has_history=False,
            status_filter=None,
            page=1,
            limit=10,
            current_user=teacher,
            db=db,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "Bạn không có quyền thực hiện chức năng này."


def test_student_action_path_registers_only_the_idempotent_handler():
    action_routes = [
        route
        for route in router.routes
        if getattr(route, "path", None)
        == "/academic/classes/{class_id}/students/{student_id}/actions"
        and "POST" in getattr(route, "methods", set())
    ]

    assert len(action_routes) == 1
    assert action_routes[0].endpoint is create_student_enrollment_action


def test_student_transfer_persists_action_and_target_enrollment(db: Session):
    _teacher, student, _second_student, _subject, source = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    target = create_class(
        ClassWrite(
            maLop="TRANSFER-TARGET",
            tenLop="Lớp đích",
            namHoc="2025-2026",
            hocVienIds=[],
            monHocIds=[],
        ),
        db,
    )
    enrollment = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == source["lopHocId"],
            LopHocHocVien.HocVienId == student.NguoiDungId,
        )
        .one()
    )

    result = create_student_enrollment_action(
        source["lopHocId"],
        student.NguoiDungId,
        ClassStudentActionWrite(
            loaiThaoTac="ChuyenLop",
            ngayHieuLuc=max(datetime.now().date(), enrollment.NgayThamGia.date()),
            lyDo="Phù hợp lịch học",
            lopHocDichId=target["lopHocId"],
        ),
        current_user=manager,
        db=db,
    )
    profile = get_student_profile(
        student.NguoiDungId,
        current_user=manager,
        db=db,
    )
    academic_profile = get_student_academic_profile(
        student.NguoiDungId,
        current_user=manager,
        db=db,
    )

    assert result["lopHocDichId"] == target["lopHocId"]
    assert profile["thaoTacs"][0]["loaiThaoTac"] == "ChuyenLop"
    assert profile["thaoTacs"][0]["maLopDich"] == target["maLop"]
    assert academic_profile["thaoTacs"][0]["ngayHieuLuc"] == result["ngayHieuLuc"]
    assert academic_profile["thaoTacs"][0]["lyDo"] == "Phù hợp lịch học"
    assert {
        item["lopHocId"] for item in profile["lopHocs"]
    } == {source["lopHocId"], target["lopHocId"]}


def test_repeating_identical_student_enrollment_action_is_idempotent(
    db: Session,
):
    _teacher, student, _second_student, _subject, source = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    enrollment = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == source["lopHocId"],
            LopHocHocVien.HocVienId == student.NguoiDungId,
        )
        .one()
    )
    request = ClassStudentActionWrite(
        loaiThaoTac="BaoLuu",
        ngayHieuLuc=max(datetime.now().date(), enrollment.NgayThamGia.date()),
        lyDo="Tạm dừng vì lý do cá nhân",
        lopHocDichId=None,
    )

    first_result = create_student_enrollment_action(
        source["lopHocId"],
        student.NguoiDungId,
        request,
        current_user=manager,
        db=db,
    )
    repeated_result = create_student_enrollment_action(
        source["lopHocId"],
        student.NguoiDungId,
        request,
        current_user=manager,
        db=db,
    )

    assert repeated_result == first_result
    assert db.query(StudentEnrollmentAction).count() == 1


def test_repeating_different_student_enrollment_action_still_conflicts(
    db: Session,
):
    _teacher, student, _second_student, _subject, source = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    enrollment = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == source["lopHocId"],
            LopHocHocVien.HocVienId == student.NguoiDungId,
        )
        .one()
    )
    request = ClassStudentActionWrite(
        loaiThaoTac="BaoLuu",
        ngayHieuLuc=max(datetime.now().date(), enrollment.NgayThamGia.date()),
        lyDo="Tạm dừng vì lý do cá nhân",
        lopHocDichId=None,
    )
    create_student_enrollment_action(
        source["lopHocId"],
        student.NguoiDungId,
        request,
        current_user=manager,
        db=db,
    )
    different_request = ClassStudentActionWrite(
        loaiThaoTac="BaoLuu",
        ngayHieuLuc=request.ngay_hieu_luc,
        lyDo="Tạm dừng vì một lý do khác",
        lopHocDichId=None,
    )

    with pytest.raises(HTTPException) as error:
        create_student_enrollment_action(
            source["lopHocId"],
            student.NguoiDungId,
            different_request,
            current_user=manager,
            db=db,
        )

    assert error.value.status_code == 409
    assert db.query(StudentEnrollmentAction).count() == 1


def test_failed_student_transfer_does_not_create_history(db: Session):
    _teacher, student, _second_student, _subject, source = setup_academic_class(db)
    manager = add_user(db, 70, 7, "Quản lý đào tạo")
    enrollment = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == source["lopHocId"],
            LopHocHocVien.HocVienId == student.NguoiDungId,
        )
        .one()
    )

    with pytest.raises(HTTPException) as error:
        create_student_enrollment_action(
            source["lopHocId"],
            student.NguoiDungId,
            ClassStudentActionWrite(
                loaiThaoTac="ChuyenLop",
                ngayHieuLuc=max(
                    datetime.now().date(),
                    enrollment.NgayThamGia.date(),
                ),
                lyDo="Lớp nguồn không thể là lớp đích",
                lopHocDichId=source["lopHocId"],
            ),
            current_user=manager,
            db=db,
        )

    assert error.value.status_code == 422
    assert db.query(StudentEnrollmentAction).count() == 0


def test_student_action_validation_requires_transfer_target():
    with pytest.raises(ValidationError):
        ClassStudentActionWrite(
            loaiThaoTac="ChuyenLop",
            ngayHieuLuc=datetime.now().date(),
            lyDo="Chuyển lớp",
        )


@pytest.mark.parametrize("reason", ["", "abc", "    "])
def test_student_action_validation_requires_meaningful_reason(reason: str):
    with pytest.raises(ValidationError):
        ClassStudentActionWrite(
            loaiThaoTac="BaoLuu",
            ngayHieuLuc=datetime.now().date(),
            lyDo=reason,
        )



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
