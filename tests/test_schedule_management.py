from datetime import date, datetime, time, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.lich_hoc import LichHocLichSu
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.phong_hoc import PhongHoc
from app.models.vai_tro import VaiTro
from app.main import app
from app.routers.schedules import (
    cancel_schedule,
    create_schedule,
    get_schedule_options,
    list_schedule_history,
    list_schedules,
    update_schedule,
)
from app.schemas.lich_hoc import LichHocCancel, LichHocWrite


def test_schedule_endpoints_are_registered():
    paths = app.openapi()["paths"]
    assert "get" in paths["/academic/schedule-options"]
    assert "get" in paths["/academic/schedules"]
    assert "post" in paths["/academic/schedules"]
    assert "put" in paths["/academic/schedules/{schedule_id}"]
    assert "post" in paths["/academic/schedules/{schedule_id}/cancel"]
    assert "get" in paths["/academic/schedule-history"]


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
        "phongHoc"
    }


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
    assert schedule["trangThaiDiemDanh"] is None

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
    assert schedules[0]["trangThaiDiemDanh"] is None
    assert options["diemDanhDuocHoTro"] is False
