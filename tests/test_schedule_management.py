from datetime import date, datetime, time, timedelta
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.lich_hoc import LichHoc, LichHocLichSu
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.phong_hoc import PhongHoc
from app.models.vai_tro import VaiTro
from app.main import app
from app.routers.schedules import (
    _acquire_schedule_write_lock,
    cancel_schedule,
    check_schedule_conflicts,
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
    assert "post" in paths["/academic/schedules/check-conflicts"]
    assert "put" in paths["/academic/schedules/{schedule_id}"]
    assert "post" in paths["/academic/schedules/{schedule_id}/cancel"]
    assert "get" in paths["/academic/schedule-history"]


def test_schedule_writes_acquire_transaction_owned_sql_server_lock():
    class FakeSession:
        def __init__(self):
            self.statement = None
            self.parameters = None

        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="mssql"))

        def execute(self, statement, parameters):
            self.statement = str(statement)
            self.parameters = parameters
            return SimpleNamespace(scalar_one=lambda: 0)

    db = FakeSession()
    _acquire_schedule_write_lock(db)

    assert "sys.sp_getapplock" in db.statement
    assert "@LockOwner = 'Transaction'" in db.statement
    assert db.parameters == {"resource": "academic-schedule-writes"}


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
    room_id: int,
    teacher_id: int,
    *,
    day: date | None = None,
    start: time = time(9),
    end: time = time(10),
    acknowledge_conflicts: bool = False,
    override_reason: str | None = None,
) -> LichHocWrite:
    return LichHocWrite(
        lopHocId=class_id,
        monHocId=subject_id,
        ngayHoc=day or date.today() + timedelta(days=10),
        gioBatDau=start,
        gioKetThuc=end,
        phongHocId=room_id,
        giangVienId=teacher_id,
        xacNhanTrungLich=acknowledge_conflicts,
        lyDoGhiDe=override_reason,
    )


def test_schedule_write_rejects_invalid_time_range():
    with pytest.raises(ValidationError, match="Giờ kết thúc phải sau giờ bắt đầu"):
        LichHocWrite(
            lopHocId=1,
            monHocId=1,
            ngayHoc=date.today(),
            gioBatDau="10:00",
            gioKetThuc="10:00",
            phongHocId=1,
            giangVienId=1,
        )

    with pytest.raises(ValidationError, match="ít nhất 5 ký tự"):
        LichHocWrite(
            lopHocId=1,
            monHocId=1,
            ngayHoc=date.today(),
            gioBatDau="09:00",
            gioKetThuc="10:00",
            phongHocId=1,
            giangVienId=1,
            xacNhanTrungLich=True,
            lyDoGhiDe="   ",
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
            room.PhongHocId,
            teacher.NguoiDungId,
            start=time(11),
            end=time(12),
        ),
        teacher,
        db,
    )

    assert changed["gioBatDau"] == "11:00"
    assert changed["phongHocId"] == room.PhongHocId
    history = list_schedule_history(teacher, db)
    assert [item["hanhDong"] for item in history] == ["Cập nhật", "Tạo"]
    assert history[0]["duLieuCu"]["gioBatDau"] == "09:00"
    assert history[0]["duLieuMoi"]["gioBatDau"] == "11:00"


    with pytest.raises(ValidationError, match="phongHocId"):
        LichHocWrite(
            lopHocId=1,
            monHocId=1,
            ngayHoc=date.today(),
            gioBatDau="09:00",
            gioKetThuc="10:00",
            giangVienId=1,
        )
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


def test_schedule_conflict_includes_primary_and_assistant_instructors(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    assistant = add_user(db, 4, 4, "Trợ giảng B")
    other_teacher = add_user(db, 6, 3, "Giảng viên C")
    db.add_all(
        [
            LopHocMonHocGiangVien(
                LopHocId=class_record.LopHocId,
                MonHocId=subject.MonHocId,
                GiangVienId=teacher.NguoiDungId,
                VaiTro="Chính",
            ),
            LopHocMonHocGiangVien(
                LopHocId=class_record.LopHocId,
                MonHocId=subject.MonHocId,
                GiangVienId=assistant.NguoiDungId,
                VaiTro="Phụ",
            ),
        ]
    )
    other_room = PhongHoc(
        PhongHocId=2,
        MaPhong="A102",
        TenPhong="Phòng A102",
        SucChua=30,
        TrangThai="Đang hoạt động",
    )
    db.add(other_room)
    db.commit()

    day = date.today() + timedelta(days=11)
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
                other_room.PhongHocId,
                other_teacher.NguoiDungId,
                day=day,
            ),
            teacher,
            db,
        )

    assert caught.value.status_code == 409
    conflicts = caught.value.detail["conflicts"]
    assert {item["ten"]: item["vaiTro"] for item in conflicts} == {
        teacher.HoTen: "Chính",
        assistant.HoTen: "Phụ",
    }


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
    conflicts = caught.value.detail["conflicts"]
    assert {item["loai"] for item in conflicts} == {"phongHoc"}
    assert {item["maBuoiHoc"] for item in conflicts} == {
        "BH-000001",
        "BH-000002",
    }
    assert all(item["ten"] == room.TenPhong for item in conflicts)
    assert all(item["maPhong"] == room.MaPhong for item in conflicts)
    assert all(item["maLop"] == class_record.MaLop for item in conflicts)
    assert all(item["tenLop"] == class_record.TenLop for item in conflicts)
    assert all(item["ngay"] == day.isoformat() for item in conflicts)
    assert {(item["gioBatDau"], item["gioKetThuc"]) for item in conflicts} == {
        ("09:00", "10:00"),
        ("10:00", "11:00"),
    }


def test_schedule_conflict_checks_shared_online_room_link(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    assistant = add_user(db, 4, 4, "Trợ giảng B")
    class_record.HinhThuc = "Trực tuyến"
    class_record.LinkTrucTuyen = "https://meet.example.com/room-a/"
    other_room = PhongHoc(
        PhongHocId=2,
        MaPhong="ONLINE-2",
        TenPhong="Phòng trực tuyến 2",
        SucChua=100,
        TrangThai="Đang hoạt động",
    )
    other_class = LopHoc(
        MaLop="CS101-02",
        TenLop="Lớp Lập trình trực tuyến 2",
        NamHoc=class_record.NamHoc,
        GiangVienId=teacher.NguoiDungId,
        NgayKhaiGiang=date.today(),
        SiSoToiDa=30,
        HinhThuc="Trực tuyến",
        PhongHocId=other_room.PhongHocId,
        LinkTrucTuyen="https://meet.example.com/other-room",
        TienDo=0,
        TrangThai="Đang học",
        NgayTao=datetime.now(),
    )
    db.add_all([other_room, other_class])
    db.flush()
    db.add(
        LopHocMonHoc(
            LopHocId=other_class.LopHocId,
            MonHocId=subject.MonHocId,
        )
    )
    db.commit()

    day = date.today() + timedelta(days=13)
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
    different_link_preview = check_schedule_conflicts(
        schedule_request(
            other_class.LopHocId,
            subject.MonHocId,
            other_room.PhongHocId,
            assistant.NguoiDungId,
            day=day,
            start=time(9, 30),
            end=time(10, 30),
        ),
        exclude_schedule_id=None,
        current_user=teacher,
        db=db,
    )
    assert different_link_preview["hasConflicts"] is False

    other_class.LinkTrucTuyen = "https://meet.example.com/room-a"
    db.commit()
    with pytest.raises(HTTPException) as caught:
        create_schedule(
            schedule_request(
                other_class.LopHocId,
                subject.MonHocId,
                other_room.PhongHocId,
                assistant.NguoiDungId,
                day=day,
                start=time(9, 30),
                end=time(10, 30),
            ),
            teacher,
            db,
        )

    assert caught.value.status_code == 409
    room_conflict = next(
        item
        for item in caught.value.detail["conflicts"]
        if item.get("linkTrucTuyen")
    )
    assert room_conflict["linkTrucTuyen"] == class_record.LinkTrucTuyen
    assert room_conflict["maLop"] == class_record.MaLop


def test_conflict_preview_returns_multiple_items_without_writing(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    substitute = add_user(db, 4, 4, "Trợ giảng B")
    day = date.today() + timedelta(days=15)
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
            room.PhongHocId,
            teacher.NguoiDungId,
            day=day,
            start=time(10),
            end=time(11),
        ),
        teacher,
        db,
    )
    history_count = db.query(LichHocLichSu).count()
    schedule_count = db.query(LichHoc).count()

    preview = check_schedule_conflicts(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            substitute.NguoiDungId,
            day=day,
            start=time(9, 30),
            end=time(10, 30),
        ),
        exclude_schedule_id=None,
        current_user=teacher,
        db=db,
    )

    assert preview["hasConflicts"] is True
    assert preview["canOverride"] is False
    assert {item["lichHocId"] for item in preview["conflicts"]} == {
        first["lichHocId"],
        second["lichHocId"],
    }
    assert {item["loai"] for item in preview["conflicts"]} == {"phongHoc"}
    assert db.query(LichHoc).count() == schedule_count
    assert db.query(LichHocLichSu).count() == history_count

    edit_preview = check_schedule_conflicts(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=day,
        ),
        exclude_schedule_id=first["lichHocId"],
        current_user=teacher,
        db=db,
    )
    assert edit_preview["hasConflicts"] is False


def test_only_training_manager_can_override_schedule_conflicts(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    manager = add_user(db, 5, 7, "Training manager")
    day = date.today() + timedelta(days=14)
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

    with pytest.raises(HTTPException) as blocked:
        create_schedule(
            schedule_request(
                class_record.LopHocId,
                subject.MonHocId,
                room.PhongHocId,
                teacher.NguoiDungId,
                day=day,
                start=time(9, 30),
                end=time(10, 30),
                acknowledge_conflicts=True,
                override_reason="Ưu tiên lịch học bù đã xác nhận.",
            ),
            teacher,
            db,
        )
    assert blocked.value.status_code == 403
    assert db.query(LichHoc).count() == 1

    request = schedule_request(
        class_record.LopHocId,
        subject.MonHocId,
        room.PhongHocId,
        teacher.NguoiDungId,
        day=day,
        start=time(9, 30),
        end=time(10, 30),
    )
    with pytest.raises(HTTPException) as warning:
        create_schedule(request, manager, db)
    assert warning.value.status_code == 409
    assert warning.value.detail["canOverride"] is True
    assert warning.value.detail["conflicts"][0]["tenLop"] == class_record.TenLop
    assert warning.value.detail["conflicts"][0]["ngay"] == day.isoformat()
    assert warning.value.detail["conflicts"][0]["gioBatDau"] == "09:00"

    acknowledged_request = schedule_request(
        class_record.LopHocId,
        subject.MonHocId,
        room.PhongHocId,
        teacher.NguoiDungId,
        day=day,
        start=time(9, 30),
        end=time(10, 30),
        acknowledge_conflicts=True,
        override_reason="Ưu tiên lịch học bù đã xác nhận.",
    )
    created = create_schedule(acknowledged_request, manager, db)
    assert created["ghiDe"] == {
        "xacNhan": True,
        "lyDo": "Ưu tiên lịch học bù đã xác nhận.",
        "soXungDot": 2,
    }
    history = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == created["lichHocId"]
    ).one()
    audit_payload = json.loads(history.DuLieuMoi)
    assert history.HanhDong == "Tạo"
    assert history.NguoiThucHienId == manager.NguoiDungId
    assert history.ThoiDiem is not None
    assert history.LyDo == "Ưu tiên lịch học bù đã xác nhận."
    assert audit_payload["xacNhanTrungLich"] is True
    assert audit_payload["lyDoGhiDe"] == "Ưu tiên lịch học bù đã xác nhận."
    assert {item["loai"] for item in audit_payload["xungDot"]} == {
        "giangVien",
        "phongHoc",
    }
    assert {item["lichHocId"] for item in audit_payload["xungDot"]} == {1}


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
    second_room = PhongHoc(
        PhongHocId=2,
        MaPhong="A102",
        TenPhong="Phòng A102",
        SucChua=30,
        TrangThai="Đang hoạt động",
    )
    db.add(second_room)
    db.commit()
    second = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            second_room.PhongHocId,
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

    manager = add_user(db, 5, 7, "Training manager")
    overridden = update_schedule(
        second["lichHocId"],
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=day,
            start=time(9, 30),
            end=time(10, 30),
            acknowledge_conflicts=True,
            override_reason="Quản lý chấp thuận xếp lịch đặc biệt.",
        ),
        manager,
        db,
    )
    assert overridden["gioBatDau"] == "09:30"
    assert overridden["ghiDe"]["lyDo"] == "Quản lý chấp thuận xếp lịch đặc biệt."
    override_history = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == second["lichHocId"],
        LichHocLichSu.HanhDong == "Cập nhật",
    ).one()
    assert json.loads(override_history.DuLieuMoi)["xacNhanTrungLich"] is True
    assert override_history.LyDo == "Quản lý chấp thuận xếp lịch đặc biệt."


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
