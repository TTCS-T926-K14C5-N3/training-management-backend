from datetime import date, datetime, time, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.diem_danh_buoi_hoc import DiemDanhBuoiHoc
from app.models.lich_hoc import LichHoc, LichHocLichSu, LichHocThongBao
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.phong_hoc import PhongHoc
from app.models.program_subject import BuoiHoc, ChuongTrinhMonHoc
from app.models.vai_tro import VaiTro
from app.main import app
from app.routers.schedules import (
    cancel_schedule,
    create_schedule,
    get_schedule_options,
    get_schedule_attendance,
    list_schedule_history,
    list_schedule_notifications,
    list_schedules,
    preview_generated_schedules,
    generate_schedules,
    save_schedule_attendance,
    update_schedule,
)
from app.schemas.lich_hoc import (
    DiemDanhBuoiHocWrite,
    LichHocCancel,
    LichHocGenerate,
    LichHocWrite,
)


def test_schedule_endpoints_are_registered():
    paths = app.openapi()["paths"]
    assert "get" in paths["/academic/schedule-options"]
    assert "get" in paths["/academic/schedules"]
    assert "post" in paths["/academic/schedules"]
    assert "post" in paths["/academic/schedules/generate-preview"]
    assert "post" in paths["/academic/schedules/generate"]
    assert "get" in paths["/academic/schedules/{schedule_id}/attendance"]
    assert "put" in paths["/academic/schedules/{schedule_id}/attendance"]
    assert "put" in paths["/academic/schedules/{schedule_id}"]
    assert "post" in paths["/academic/schedules/{schedule_id}/cancel"]
    assert "get" in paths["/academic/schedule-history"]
    assert "get" in paths["/academic/schedule-notifications"]


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
    role = db.query(VaiTro).filter(VaiTro.VaiTroId == role_id).first()
    if role is None:
        db.add(VaiTro(VaiTroId=role_id, TenVaiTro=f"Vai trò {role_id}"))
    user = NguoiDung(
        NguoiDungId=user_id,
        HoTen=name,
        Email=f"user{user_id}@example.com",
        MatKhauHash="test-hash",
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
    db.flush()
    return user


def setup_schedule_context(db: Session):
    teacher = add_user(db, 3, 3, "Giảng viên A")
    room = PhongHoc(
        PhongHocId=1,
        MaPhong="A101",
        TenPhong="Phòng A101",
        SucChua=30,
        TrangThai="Đang hoạt động",
    )
    subject = MonHoc(
        MaMonHoc="CS101",
        TenMonHoc="Lập trình",
        SoTinChi=3,
        SoBuoi=10,
        TrongSo=1,
        TrangThai="Đang hoạt động",
    )
    class_record = LopHoc(
        MaLop="CS101-01",
        TenLop="Lớp Lập trình",
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
    db.add_all([room, subject, class_record])
    db.flush()
    db.add(
        LopHocMonHoc(
            LopHocId=class_record.LopHocId,
            MonHocId=subject.MonHocId,
        )
    )
    db.commit()
    return teacher, room, subject, class_record


def schedule_request(
    class_id: int,
    subject_id: int,
    room_id: int | None,
    teacher_id: int,
    *,
    day: date | None = None,
    start: time = time(9),
    end: time = time(10),
) -> LichHocWrite:
    return LichHocWrite(
        lopHocId=class_id,
        monHocId=subject_id,
        ngayHoc=day or date.today() + timedelta(days=10),
        gioBatDau=start,
        gioKetThuc=end,
        phongHocId=room_id,
        giangVienId=teacher_id,
    )


def generator_request(
    class_id: int,
    subject_id: int,
    room_id: int | None,
    teacher_id: int,
    start_date: date,
    *,
    session_count: int = 3,
    weekdays: list[int] | None = None,
    holidays: list[date] | None = None,
) -> LichHocGenerate:
    return LichHocGenerate(
        lopHocId=class_id,
        monHocId=subject_id,
        ngayBatDau=start_date,
        thuTrongTuan=weekdays or [start_date.isoweekday()],
        soBuoi=session_count,
        gioBatDau=time(9),
        gioKetThuc=time(10),
        phongHocId=room_id,
        giangVienId=teacher_id,
        ngayNghi=holidays or [],
    )


def setup_curriculum_lessons(
    db: Session,
    class_record: LopHoc,
    subject: MonHoc,
    lesson_count: int = 5,
) -> list[BuoiHoc]:
    program = ChuongTrinhDaoTao(
        MaChuongTrinh=f"TEST-{class_record.LopHocId}",
        TenChuongTrinh="Chương trình kiểm thử",
        TongThoiLuong=lesson_count,
        HocPhiChuan=0,
        NgayTao=datetime.now(),
    )
    db.add(program)
    db.flush()
    class_record.ChuongTrinhId = program.ChuongTrinhId
    association = ChuongTrinhMonHoc(
        ChuongTrinhId=program.ChuongTrinhId,
        MonHocId=subject.MonHocId,
        ThuTu=1,
    )
    db.add(association)
    db.flush()
    lessons = [
        BuoiHoc(
            ChuongTrinhMonHocId=association.ChuongTrinhMonHocId,
            SoThuTu=index,
            ChuDe=f"Bài học {index}",
        )
        for index in range(1, lesson_count + 1)
    ]
    db.add_all(lessons)
    db.commit()
    return lessons


def test_schedule_write_rejects_invalid_time_range():
    with pytest.raises(ValidationError, match="Giờ kết thúc phải sau giờ bắt đầu"):
        LichHocWrite(
            lopHocId=1,
            monHocId=1,
            ngayHoc=date.today(),
            gioBatDau="10:00",
            gioKetThuc="10:00",
            giangVienId=1,
        )


def test_create_update_and_persist_schedule_history(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
        ),
        teacher,
        db,
    )
    changed = update_schedule(
        schedule["lichHocId"],
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            None,
            teacher.NguoiDungId,
            start=time(11),
            end=time(12),
        ),
        teacher,
        db,
    )

    assert changed["gioBatDau"] == "11:00"
    assert changed["phongHocId"] is None
    history = list_schedule_history(teacher, db)
    assert [item["hanhDong"] for item in history] == ["Cập nhật", "Tạo"]
    assert history[0]["duLieuCu"]["gioBatDau"] == "09:00"
    assert history[0]["duLieuMoi"]["gioBatDau"] == "11:00"


def test_schedule_update_notifies_students_and_old_and_new_instructors(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 5, 2, "Học viên A")
    substitute = add_user(db, 4, 4, "Trợ giảng B")
    db.add(
        LopHocHocVien(
            LopHocId=class_record.LopHocId,
            HocVienId=student.NguoiDungId,
            NgayThamGia=datetime.now(),
        )
    )
    db.commit()
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
        ),
        teacher,
        db,
    )

    update_schedule(
        schedule["lichHocId"],
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            substitute.NguoiDungId,
            day=date.today() + timedelta(days=11),
            start=time(10),
            end=time(11),
        ),
        teacher,
        db,
    )

    assert db.query(LichHocThongBao).count() == 3
    student_notifications = list_schedule_notifications(student, db)
    assert len(student_notifications) == 1
    assert student_notifications[0]["title"] == "Lịch học đã thay đổi"
    assert "giảng viên: Trợ giảng B" in student_notifications[0]["message"]
    assert list_schedule_notifications(teacher, db)[0]["title"] == "Lịch học đã thay đổi"
    assert list_schedule_notifications(substitute, db)[0]["title"] == "Lịch học đã thay đổi"


def test_schedule_with_attendance_cannot_be_updated_or_cancelled(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 5, 2, "Học viên A")
    db.add(
        LopHocHocVien(
            LopHocId=class_record.LopHocId,
            HocVienId=student.NguoiDungId,
            NgayThamGia=datetime.now(),
        )
    )
    db.commit()
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
        ),
        teacher,
        db,
    )
    db.add(
        DiemDanhBuoiHoc(
            LichHocId=schedule["lichHocId"],
            HocVienId=student.NguoiDungId,
            TrangThai="Có mặt",
            NgayCapNhat=datetime.now(),
            NguoiCapNhatId=teacher.NguoiDungId,
        )
    )
    db.commit()

    payload = list_schedules(None, None, None, teacher, db)[0]
    assert payload["coTheChinhSua"] is False
    assert payload["coTheHuy"] is False
    with pytest.raises(HTTPException) as update_error:
        update_schedule(
            schedule["lichHocId"],
            schedule_request(
                class_record.LopHocId,
                subject.MonHocId,
                room.PhongHocId,
                teacher.NguoiDungId,
                day=date.today() + timedelta(days=11),
            ),
            teacher,
            db,
        )
    assert update_error.value.status_code == 409
    assert "đã có dữ liệu điểm danh" in update_error.value.detail
    with pytest.raises(HTTPException) as cancel_error:
        cancel_schedule(
            schedule["lichHocId"],
            LichHocCancel(lyDo="Giảng viên bận"),
            teacher,
            db,
        )
    assert cancel_error.value.status_code == 409
    assert "đã có dữ liệu điểm danh" in cancel_error.value.detail
    assert [item.HanhDong for item in db.query(LichHocLichSu).all()] == ["Tạo"]
    assert db.query(LichHocThongBao).count() == 0


def test_schedule_conflict_reports_teacher_and_room_details(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    day = date.today() + timedelta(days=10)
    create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=day,
        ),
        teacher,
        db,
    )

    with pytest.raises(HTTPException) as caught:
        create_schedule(
            schedule_request(
                class_record.LopHocId,
                subject.MonHocId,
                room.PhongHocId,
                teacher.NguoiDungId,
                day=day,
                start=time(9, 30),
                end=time(10, 30),
            ),
            teacher,
            db,
        )

    assert caught.value.status_code == 409
    detail = caught.value.detail
    assert {item["loai"] for item in detail["conflicts"]} == {
        "lopHoc",
        "giangVien",
        "phongHoc",
    }
    assert all(item["maBuoiHoc"] == "BH-000001" for item in detail["conflicts"])


def test_schedule_conflict_checks_room_and_allows_adjacent_time_slots(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    substitute = add_user(db, 4, 4, "Trợ giảng B")
    day = date.today() + timedelta(days=12)
    create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=day,
        ),
        teacher,
        db,
    )
    adjacent = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=day,
            start=time(10),
            end=time(11),
        ),
        teacher,
        db,
    )
    assert adjacent["gioBatDau"] == "10:00"

    with pytest.raises(HTTPException) as caught:
        create_schedule(
            schedule_request(
                class_record.LopHocId,
                subject.MonHocId,
                room.PhongHocId,
                substitute.NguoiDungId,
                day=day,
                start=time(9, 30),
                end=time(10, 30),
            ),
            teacher,
            db,
        )

    assert caught.value.status_code == 409
    assert {item["loai"] for item in caught.value.detail["conflicts"]} == {
        "lopHoc",
        "phongHoc"
    }


def test_bulk_schedule_preview_skips_holidays_and_persists_lesson_history(
    db: Session,
):
    teacher, room, subject, class_record = setup_schedule_context(db)
    lessons = setup_curriculum_lessons(db, class_record, subject)
    first_monday = date.today() + timedelta(days=1)
    while first_monday.isoweekday() != 1:
        first_monday += timedelta(days=1)
    request = generator_request(
        class_record.LopHocId,
        subject.MonHocId,
        room.PhongHocId,
        teacher.NguoiDungId,
        first_monday,
        session_count=3,
        weekdays=[1],
        holidays=[first_monday],
    )

    preview = preview_generated_schedules(request, teacher, db)
    assert preview["skippedHolidays"] == [first_monday.isoformat()]
    assert [item["ngayHoc"] for item in preview["sessions"]] == [
        (first_monday + timedelta(days=7)).isoformat(),
        (first_monday + timedelta(days=14)).isoformat(),
        (first_monday + timedelta(days=21)).isoformat(),
    ]
    assert [item["buoiHocId"] for item in preview["sessions"]] == [
        item.BuoiHocId for item in lessons[:3]
    ]
    options = get_schedule_options(teacher, db)
    assert options["lopHocs"][0]["monHocs"][0]["buoiHocs"][0]["chuDe"] == "Bài học 1"

    created = generate_schedules(request, teacher, db)
    assert len(created) == 3
    assert [item["chuDeBuoiHoc"] for item in created] == [
        "Bài học 1",
        "Bài học 2",
        "Bài học 3",
    ]
    assert db.query(LichHocLichSu).count() == 3
    assert len(list_schedule_history(teacher, db)) == 3


def test_bulk_schedule_preview_supports_sixty_sessions(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    setup_curriculum_lessons(db, class_record, subject, lesson_count=60)
    first_monday = date.today() + timedelta(days=1)
    while first_monday.isoweekday() != 1:
        first_monday += timedelta(days=1)
    request = generator_request(
        class_record.LopHocId,
        subject.MonHocId,
        room.PhongHocId,
        teacher.NguoiDungId,
        first_monday,
        session_count=60,
        weekdays=[1, 2, 3, 4, 5],
    )

    preview = preview_generated_schedules(request, teacher, db)

    assert len(preview["sessions"]) == 60
    assert preview["sessions"][0]["soThuTu"] == 1
    assert preview["sessions"][-1]["soThuTu"] == 60
    assert all(
        date.fromisoformat(item["ngayHoc"]).isoweekday() in {1, 2, 3, 4, 5}
        for item in preview["sessions"]
    )


def test_bulk_schedule_conflict_does_not_create_partial_batch(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    setup_curriculum_lessons(db, class_record, subject)
    first_day = date.today() + timedelta(days=1)
    while first_day.isoweekday() != 1:
        first_day += timedelta(days=1)
    request = generator_request(
        class_record.LopHocId,
        subject.MonHocId,
        room.PhongHocId,
        teacher.NguoiDungId,
        first_day,
        session_count=3,
        weekdays=[1],
    )
    create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=first_day,
        ),
        teacher,
        db,
    )

    preview = preview_generated_schedules(request, teacher, db)
    assert len(preview["conflicts"]) == 3
    with pytest.raises(HTTPException) as caught:
        generate_schedules(request, teacher, db)

    assert caught.value.status_code == 409
    assert db.query(LichHocLichSu).count() == 1
    assert db.query(LichHoc).count() == 1


def test_update_schedule_rejects_conflict_without_changing_existing_schedule(
    db: Session,
):
    teacher, room, subject, class_record = setup_schedule_context(db)
    substitute = add_user(db, 4, 4, "Trợ giảng B")
    day = date.today() + timedelta(days=12)
    first = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=day,
        ),
        teacher,
        db,
    )
    second = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            None,
            substitute.NguoiDungId,
            day=day,
            start=time(11),
            end=time(12),
        ),
        teacher,
        db,
    )

    with pytest.raises(HTTPException) as caught:
        update_schedule(
            second["lichHocId"],
            schedule_request(
                class_record.LopHocId,
                subject.MonHocId,
                room.PhongHocId,
                teacher.NguoiDungId,
                day=day,
                start=time(9, 30),
                end=time(10, 30),
            ),
            teacher,
            db,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail["conflicts"][0]["lichHocId"] == first["lichHocId"]
    unchanged = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == second["lichHocId"]
    ).all()
    assert [item.HanhDong for item in unchanged] == ["Tạo"]


def test_cancel_requires_reason_and_writes_audit_entry(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 5, 2, "Học viên A")
    db.add(
        LopHocHocVien(
            LopHocId=class_record.LopHocId,
            HocVienId=student.NguoiDungId,
            NgayThamGia=datetime.now(),
        )
    )
    db.commit()
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
        ),
        teacher,
        db,
    )
    with pytest.raises(ValidationError, match="Vui lòng nhập lý do hủy"):
        LichHocCancel(lyDo="   ")

    cancelled = cancel_schedule(
        schedule["lichHocId"],
        LichHocCancel(lyDo="  Giảng viên bận  "),
        teacher,
        db,
    )
    assert cancelled["trangThai"] == "Đã hủy"
    assert cancelled["lyDoHuy"] == "Giảng viên bận"
    assert db.query(LichHocLichSu).filter(
        LichHocLichSu.HanhDong == "Hủy"
    ).count() == 1
    notifications = list_schedule_notifications(teacher, db)
    assert len(notifications) == 1
    assert notifications[0]["title"] == "Buổi học đã bị hủy"
    assert "Giảng viên bận" in notifications[0]["message"]
    student_notifications = list_schedule_notifications(student, db)
    assert len(student_notifications) == 1
    assert student_notifications[0]["title"] == "Buổi học đã bị hủy"
    assert "Giảng viên bận" in student_notifications[0]["message"]

    with pytest.raises(HTTPException) as caught:
        cancel_schedule(
            schedule["lichHocId"],
            LichHocCancel(lyDo="Hủy lần nữa"),
            teacher,
            db,
        )
    assert caught.value.status_code == 409


def test_update_does_not_allow_changing_class_or_subject(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
        ),
        teacher,
        db,
    )
    request = schedule_request(
        class_record.LopHocId,
        subject.MonHocId,
        room.PhongHocId,
        teacher.NguoiDungId,
    )
    request.lop_hoc_id += 1

    with pytest.raises(HTTPException) as caught:
        update_schedule(schedule["lichHocId"], request, teacher, db)
    assert caught.value.status_code == 422


def test_started_schedule_cannot_be_edited_or_cancelled(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=date.today() - timedelta(days=1),
        ),
        teacher,
        db,
    )
    assert schedule["trangThai"] == "Đã diễn ra"
    assert schedule["coTheChinhSua"] is False
    assert schedule["coTheHuy"] is False
    assert schedule["trangThaiDiemDanh"] == "Chưa điểm danh"

    with pytest.raises(HTTPException) as edit_error:
        update_schedule(
            schedule["lichHocId"],
            schedule_request(
                class_record.LopHocId,
                subject.MonHocId,
                room.PhongHocId,
                teacher.NguoiDungId,
                day=date.today() + timedelta(days=1),
            ),
            teacher,
            db,
        )
    with pytest.raises(HTTPException) as cancel_error:
        cancel_schedule(
            schedule["lichHocId"],
            LichHocCancel(lyDo="Hủy buổi đã qua"),
            teacher,
            db,
        )

    assert edit_error.value.status_code == 409
    assert cancel_error.value.status_code == 409


def test_list_schedules_only_returns_accessible_class_schedules(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    created = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
        ),
        teacher,
        db,
    )

    schedules = list_schedules(None, None, None, teacher, db)
    options = get_schedule_options(teacher, db)

    assert [item["lichHocId"] for item in schedules] == [created["lichHocId"]]
    assert schedules[0]["trangThaiDiemDanh"] == "Chưa điểm danh"
    assert options["diemDanhDuocHoTro"] is True


def test_schedule_attendance_can_be_read_and_saved_per_session(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 20, 2, "Học viên A")
    db.add(
        LopHocHocVien(
            LopHocId=class_record.LopHocId,
            HocVienId=student.NguoiDungId,
            NgayThamGia=datetime.now(),
        )
    )
    db.commit()
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
        ),
        teacher,
        db,
    )

    initial = get_schedule_attendance(schedule["lichHocId"], teacher, db)
    assert initial["records"][0]["trangThai"] is None
    assert initial["coTheCapNhat"] is True

    saved = save_schedule_attendance(
        schedule["lichHocId"],
        DiemDanhBuoiHocWrite(
            records=[{"hocVienId": student.NguoiDungId, "trangThai": "Có mặt"}]
        ),
        teacher,
        db,
    )
    assert saved["records"][0]["trangThai"] == "Có mặt"
    assert db.query(DiemDanhBuoiHoc).count() == 1

    updated = save_schedule_attendance(
        schedule["lichHocId"],
        DiemDanhBuoiHocWrite(
            records=[{"hocVienId": student.NguoiDungId, "trangThai": "Đi muộn"}]
        ),
        teacher,
        db,
    )
    assert updated["records"][0]["trangThai"] == "Đi muộn"
    assert db.query(DiemDanhBuoiHoc).count() == 1

    student_view = get_schedule_attendance(schedule["lichHocId"], student, db)
    assert student_view["records"][0]["trangThai"] == "Đi muộn"
    assert student_view["coTheCapNhat"] is False


def test_schedule_attendance_rejects_students_not_enrolled_in_class(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 21, 2, "Học viên ngoài lớp")
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
        ),
        teacher,
        db,
    )

    with pytest.raises(HTTPException) as caught:
        save_schedule_attendance(
            schedule["lichHocId"],
            DiemDanhBuoiHocWrite(
                records=[{"hocVienId": student.NguoiDungId, "trangThai": "Có mặt"}]
            ),
            teacher,
            db,
        )

    assert caught.value.status_code == 422
    assert db.query(DiemDanhBuoiHoc).count() == 0
