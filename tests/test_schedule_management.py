import asyncio
from datetime import date, datetime, time, timedelta, timezone
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import get_current_user
from app.database import Base, get_db
from app.models.diem_danh import DiemDanh
from app.models.absence_request import AttendanceAudit, AttendanceNotification
from app.models.lich_hoc import LichHoc, LichHocLichSu
from app.models.lich_hoc_thong_bao import LichHocThongBao
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.phong_hoc import PhongHoc
from app.models.quyen import Quyen
from app.models.student_enrollment_action import StudentEnrollmentAction
from app.models.vai_tro import VaiTro
from app.models.vai_tro_quyen import VaiTroQuyen
from app.main import app
from app.routers import schedules as schedules_router
from app.routers.schedules import (
    _acquire_schedule_write_lock,
    cancel_schedule,
    check_schedule_conflicts,
    create_schedule,
    get_schedule_attendance,
    get_schedule_options,
    list_completed_schedules,
    list_schedule_history,
    list_schedules,
    update_schedule,
    update_schedule_attendance,
)
from app.routers.attendance import (
    create_absence_request as create_absence_request_service,
    decide_absence_request,
)
from app.schemas.lich_hoc import DiemDanhWrite, LichHocCancel, LichHocWrite
from app.schemas.attendance import AbsenceRequestDecision, AbsenceRequestWrite
from app.services import business_time
from app.services import schedule_notifications


def test_schedule_endpoints_are_registered():
    paths = app.openapi()["paths"]
    assert "get" in paths["/academic/schedule-options"]
    assert "get" in paths["/academic/schedules"]
    assert "get" in paths["/academic/schedules/completed"]
    assert "post" in paths["/academic/schedules"]
    assert "post" in paths["/academic/schedules/check-conflicts"]
    assert "put" in paths["/academic/schedules/{schedule_id}"]
    assert "post" in paths["/academic/schedules/{schedule_id}/cancel"]
    assert "get" in paths["/academic/schedule-history"]
    assert "post" in paths["/academic/schedule-notifications/retry"]
    assert "get" in paths["/academic/schedules/{schedule_id}/attendance"]
    assert "put" in paths["/academic/schedules/{schedule_id}/attendance"]
    assert "get" in paths["/attendance/absence-requests"]
    assert "post" in paths["/attendance/absence-requests"]
    assert "post" in paths[
        "/attendance/absence-requests/{request_id}/decision"
    ]
    assert "get" in paths["/attendance/my-history"]
    assert "get" in paths["/attendance/notifications"]
    assert "get" in paths["/attendance/schedules/{schedule_id}/audit"]
    history_parameters = {
        item["name"]
        for item in paths["/academic/schedule-history"]["get"]["parameters"]
    }
    assert {"page", "pageSize", "q", "eventType"} <= history_parameters


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "put",
            "/academic/schedules/1",
            {
                "lopHocId": 1,
                "monHocId": 1,
                "ngayHoc": "2030-01-02",
                "gioBatDau": "09:00",
                "gioKetThuc": "10:00",
                "phongHocId": 1,
                "giangVienId": 1,
            },
        ),
        (
            "post",
            "/academic/schedules/1/cancel",
            {"lyDo": "Giảng viên bận"},
        ),
        (
            "post",
            "/academic/schedule-notifications/retry",
            {},
        ),
    ],
)
def test_schedule_write_endpoints_reject_unauthenticated_requests(
    method: str,
    path: str,
    payload: dict,
):
    test_app = FastAPI()
    test_app.include_router(schedules_router.router)
    test_app.dependency_overrides[get_db] = lambda: object()

    with TestClient(test_app) as client:
        response = client.request(method, path, json=payload)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        (
            "put",
            "/academic/schedules/1",
            {
                "lopHocId": 1,
                "monHocId": 1,
                "ngayHoc": "2030-01-02",
                "gioBatDau": "09:00",
                "gioKetThuc": "10:00",
                "phongHocId": 1,
                "giangVienId": 1,
            },
        ),
        (
            "post",
            "/academic/schedules/1/cancel",
            {"lyDo": "Giảng viên bận"},
        ),
        (
            "post",
            "/academic/schedule-notifications/retry",
            {},
        ),
    ],
)
def test_schedule_write_endpoints_reject_users_without_permission(
    method: str,
    path: str,
    payload: dict,
):
    class DenyingPermissionDatabase:
        def execute(self, _query, _parameters):
            return SimpleNamespace(first=lambda: None)

    test_app = FastAPI()
    test_app.include_router(schedules_router.router)
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        NguoiDungId=3
    )
    test_app.dependency_overrides[get_db] = DenyingPermissionDatabase

    with TestClient(test_app) as client:
        response = client.request(method, path, json=payload)

    assert response.status_code == 403


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


@pytest.fixture(autouse=True)
def disable_schedule_email_delivery(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        schedule_notifications,
        "send_schedule_change_email",
        lambda _email, _name, _content: None,
    )


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


def grant_permission(db: Session, user: NguoiDung, permission_code: str) -> None:
    permission = Quyen(
        MaQuyen=permission_code,
        TenQuyen=permission_code,
    )
    db.add(permission)
    db.flush()
    role_id = db.query(NguoiDungVaiTro.VaiTroId).filter(
        NguoiDungVaiTro.NguoiDungId == user.NguoiDungId
    ).scalar()
    db.add(VaiTroQuyen(VaiTroId=role_id, QuyenId=permission.QuyenId))
    db.flush()


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
    values = {
        "lop_hoc_id": class_id,
        "mon_hoc_id": subject_id,
        "ngay_hoc": day or business_time.business_now().date() + timedelta(days=10),
        "gio_bat_dau": start,
        "gio_ket_thuc": end,
        "phong_hoc_id": room_id,
        "giang_vien_id": teacher_id,
        "xac_nhan_trung_lich": acknowledge_conflicts,
        "ly_do_ghi_de": override_reason,
    }
    now = business_time.business_now()
    if values["ngay_hoc"] < now.date() or (
        values["ngay_hoc"] == now.date()
        and start <= now.timetz().replace(tzinfo=None)
    ):
        return LichHocWrite.model_construct(**values)
    return LichHocWrite(**values)


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


def test_schedule_write_requires_a_room():
    with pytest.raises(ValidationError):
        LichHocWrite(
            lopHocId=1,
            monHocId=1,
            ngayHoc="2030-05-10",
            gioBatDau="09:00",
            gioKetThuc="10:00",
            phongHocId=None,
            giangVienId=1,
        )


def test_schedule_write_enforces_business_date_and_future_time(
    monkeypatch: pytest.MonkeyPatch,
):
    frozen_now = datetime(
        2030,
        5,
        10,
        12,
        30,
        tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
    )
    monkeypatch.setattr(business_time, "business_now", lambda: frozen_now)
    payload = {
        "lopHocId": 1,
        "monHocId": 1,
        "phongHocId": 1,
        "giangVienId": 1,
    }

    with pytest.raises(ValidationError, match="Ngày học không được nằm trong quá khứ"):
        LichHocWrite(
            **payload,
            ngayHoc="2030-05-09",
            gioBatDau="13:00",
            gioKetThuc="14:00",
        )
    with pytest.raises(ValidationError, match="kết thúc sau thời điểm hiện tại"):
        LichHocWrite(
            **payload,
            ngayHoc="2030-05-10",
            gioBatDau="10:00",
            gioKetThuc="12:00",
        )
    with pytest.raises(ValidationError, match="bắt đầu sau thời điểm hiện tại"):
        LichHocWrite(
            **payload,
            ngayHoc="2030-05-10",
            gioBatDau="12:00",
            gioKetThuc="13:00",
        )

    valid = LichHocWrite(
        **payload,
        ngayHoc="2030-05-10",
        gioBatDau="12:31",
        gioKetThuc="13:00",
    )
    assert valid.ngay_hoc == date(2030, 5, 10)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/academic/schedules"),
        ("put", "/academic/schedules/1"),
    ],
)
def test_schedule_api_rejects_past_date_without_frontend_validation(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
):
    frozen_now = datetime(
        2030,
        5,
        10,
        12,
        30,
        tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"),
    )
    monkeypatch.setattr(business_time, "business_now", lambda: frozen_now)
    test_app = FastAPI()
    test_app.include_router(schedules_router.router)
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        NguoiDungId=1
    )

    class GrantingPermissionDatabase:
        def execute(self, _query, _parameters):
            return SimpleNamespace(first=lambda: SimpleNamespace())

    test_app.dependency_overrides[get_db] = GrantingPermissionDatabase

    payload = {
        "lopHocId": 1,
        "monHocId": 1,
        "ngayHoc": "2030-05-09",
        "gioBatDau": "13:00",
        "gioKetThuc": "14:00",
        "phongHocId": 1,
        "giangVienId": 1,
    }
    with TestClient(test_app) as client:
        response = client.request(method, path, json=payload)

    assert response.status_code == 422
    assert "Ngày học không được nằm trong quá khứ" in response.text


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
    history = list_schedule_history(teacher, db)["items"]
    assert [item["hanhDong"] for item in history] == ["Cập nhật", "Tạo"]
    assert history[0]["duLieuCu"]["gioBatDau"] == "09:00"
    assert history[0]["duLieuMoi"]["gioBatDau"] == "11:00"


def test_schedule_history_search_filter_and_pagination(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    second_room = PhongHoc(
        MaPhong="B202",
        TenPhong="Phòng B202",
        SucChua=30,
        TrangThai="Đang hoạt động",
    )
    substitute = add_user(db, 4, 4, "Trợ giảng B")
    db.add(second_room)
    db.commit()
    first_day = business_time.business_now().date() + timedelta(days=20)
    first = create_schedule(
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
    update_schedule(
        first["lichHocId"],
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            second_room.PhongHocId,
            substitute.NguoiDungId,
            day=first_day + timedelta(days=1),
            start=time(11),
            end=time(12),
        ),
        teacher,
        db,
    )
    create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=first_day + timedelta(days=2),
        ),
        teacher,
        db,
    )

    page = list_schedule_history(teacher, db, page=1, page_size=1)
    assert page["total"] == 3
    assert page["page"] == 1
    assert page["pageSize"] == 1
    assert len(page["items"]) == 1

    by_schedule_code = list_schedule_history(
        teacher,
        db,
        search=f"BH-{first['lichHocId']:06d}",
    )
    assert by_schedule_code["total"] == 2

    by_notice_text = list_schedule_history(
        teacher,
        db,
        search="ĐÃ THAY ĐỔI LỊCH",
    )
    assert by_notice_text["total"] == 1
    assert "đã thay đổi lịch" in by_notice_text["items"][0]["noiDungThongBao"]
    assert by_notice_text["items"][0]["trangThaiThongBao"] == {
        "total": 2,
        "sent": 2,
        "failed": 0,
        "pending": 0,
    }

    room_changes = list_schedule_history(
        teacher,
        db,
        event_type="room",
        page=1,
        page_size=10,
    )
    assert room_changes["total"] == 1
    assert room_changes["items"][0]["duLieuCu"]["phongHocId"] == room.PhongHocId
    assert room_changes["items"][0]["duLieuMoi"]["phongHocId"] == second_room.PhongHocId

    no_results = list_schedule_history(
        teacher,
        db,
        search="không tồn tại",
    )
    assert no_results == {"items": [], "total": 0, "page": 1, "pageSize": 20}


    with pytest.raises(ValidationError, match="phongHocId"):
        LichHocWrite(
            lopHocId=1,
            monHocId=1,
            ngayHoc=date.today(),
            gioBatDau="09:00",
            gioKetThuc="10:00",
            giangVienId=1,
        )
    with pytest.raises(ValidationError, match="ngayHoc"):
        LichHocWrite(
            lopHocId=1,
            monHocId=1,
            ngayHoc="not-a-date",
            gioBatDau="09:00",
            gioKetThuc="10:00",
            phongHocId=1,
            giangVienId=1,
        )
    with pytest.raises(ValidationError, match="không kèm múi giờ"):
        LichHocWrite(
            lopHocId=1,
            monHocId=1,
            ngayHoc=date.today(),
            gioBatDau=time(9, tzinfo=timezone.utc),
            gioKetThuc=time(10),
            phongHocId=1,
            giangVienId=1,
        )
def test_update_schedule_rejects_any_recorded_attendance_without_changes(
    db: Session,
):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 20, 2, "Học viên đã điểm danh")
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
        DiemDanh(
            LichHocId=schedule["lichHocId"],
            HocVienId=student.NguoiDungId,
            TrangThai="Có mặt",
            NguoiDiemDanhId=teacher.NguoiDungId,
            NgayCapNhat=datetime.now(),
        )
    )
    db.commit()

    with pytest.raises(HTTPException) as caught:
        update_schedule(
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

    assert caught.value.status_code == 409
    saved_schedule = db.query(LichHoc).filter(
        LichHoc.LichHocId == schedule["lichHocId"]
    ).one()
    assert saved_schedule.GioBatDau == time(9)
    assert saved_schedule.GioKetThuc == time(10)
    assert db.query(DiemDanh).filter(
        DiemDanh.LichHocId == schedule["lichHocId"]
    ).count() == 1
    history = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == schedule["lichHocId"]
    ).all()
    assert [item.HanhDong for item in history] == ["Tạo"]
    assert db.query(LichHocThongBao).count() == 0


def test_update_schedule_not_found_returns_404(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)

    with pytest.raises(HTTPException) as caught:
        update_schedule(
            999,
            schedule_request(
                class_record.LopHocId,
                subject.MonHocId,
                room.PhongHocId,
                teacher.NguoiDungId,
            ),
            teacher,
            db,
        )

    assert caught.value.status_code == 404


def test_update_schedule_rejects_unknown_room_and_instructor(
    db: Session,
):
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
    invalid_references = (
        (999, teacher.NguoiDungId),
        (room.PhongHocId, 999),
    )
    for invalid_room_id, invalid_teacher_id in invalid_references:
        with pytest.raises(HTTPException) as caught:
            update_schedule(
                schedule["lichHocId"],
                schedule_request(
                    class_record.LopHocId,
                    subject.MonHocId,
                    invalid_room_id,
                    invalid_teacher_id,
                    start=time(11),
                    end=time(12),
                ),
                teacher,
                db,
            )
        assert caught.value.status_code == 422

    saved_schedule = db.query(LichHoc).filter(
        LichHoc.LichHocId == schedule["lichHocId"]
    ).one()
    assert saved_schedule.PhongHocId == room.PhongHocId
    assert saved_schedule.GiangVienId == teacher.NguoiDungId
    history = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == schedule["lichHocId"]
    ).all()
    assert [item.HanhDong for item in history] == ["Tạo"]


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


def test_schedule_conflicts_require_permission_and_audit_override(db: Session):
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
    assert blocked.value.status_code == 409
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
    assert warning.value.detail["canOverride"] is False
    assert warning.value.detail["conflicts"][0]["tenLop"] == class_record.TenLop
    assert warning.value.detail["conflicts"][0]["ngay"] == day.isoformat()
    assert warning.value.detail["conflicts"][0]["gioBatDau"] == "09:00"

    grant_permission(db, manager, "SCHEDULE_OVERRIDE")
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
    history = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == created["lichHocId"]
    ).one()
    assert db.query(LichHoc).count() == 2
    assert history.LyDo == "Ưu tiên lịch học bù đã xác nhận."


def test_update_schedule_requires_permission_before_overriding_conflict(
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
    with pytest.raises(HTTPException) as manager_conflict:
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
                acknowledge_conflicts=True,
                override_reason="Quản lý chấp thuận xếp lịch đặc biệt.",
            ),
            manager,
            db,
        )
    assert manager_conflict.value.status_code == 409
    unchanged = db.query(LichHoc).filter(
        LichHoc.LichHocId == second["lichHocId"]
    ).one()
    assert unchanged.GioBatDau == time(11)
    override_history = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == second["lichHocId"],
    ).all()
    assert [item.HanhDong for item in override_history] == ["Tạo"]
    assert db.query(LichHocThongBao).count() == 0

    grant_permission(db, manager, "SCHEDULE_OVERRIDE")
    updated = update_schedule(
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
    assert updated["gioBatDau"] == "09:30"
    override_history = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == second["lichHocId"],
    ).all()
    assert [item.HanhDong for item in override_history] == ["Tạo", "Cập nhật"]
    assert override_history[-1].LyDo == "Quản lý chấp thuận xếp lịch đặc biệt."
    assert db.query(LichHocThongBao).count() > 0


def test_update_schedule_excludes_itself_and_allows_adjacent_slots(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    day = date.today() + timedelta(days=14)
    first = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=day,
            start=time(9),
            end=time(10),
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

    unchanged = update_schedule(
        first["lichHocId"],
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=day,
            start=time(9),
            end=time(10),
        ),
        teacher,
        db,
    )
    adjacent_update = update_schedule(
        adjacent["lichHocId"],
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

    assert unchanged["gioBatDau"] == "09:00"
    assert adjacent_update["gioBatDau"] == "10:00"
    assert adjacent_update["gioKetThuc"] == "11:00"


def test_update_schedule_rolls_back_schedule_and_history_on_commit_error(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
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

    def fail_commit():
        raise IntegrityError(
            "UPDATE LichHoc",
            {},
            RuntimeError("simulated constraint failure"),
        )

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(HTTPException) as caught:
        update_schedule(
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
    monkeypatch.undo()

    assert caught.value.status_code == 409
    saved_schedule = db.query(LichHoc).filter(
        LichHoc.LichHocId == schedule["lichHocId"]
    ).one()
    assert saved_schedule.GioBatDau == time(9)
    assert saved_schedule.GioKetThuc == time(10)
    history = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == schedule["lichHocId"]
    ).all()
    assert [item.HanhDong for item in history] == ["Tạo"]
    assert db.query(LichHocThongBao).count() == 0


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
    with pytest.raises(ValidationError):
        LichHocCancel()

    cancelled = cancel_schedule(
        schedule["lichHocId"],
        LichHocCancel(lyDo="  Giảng viên bận  "),
        teacher,
        db,
    )
    assert cancelled["trangThai"] == "Đã hủy"
    assert cancelled["lyDoHuy"] == "Giảng viên bận"
    saved_schedule = db.query(LichHoc).filter(
        LichHoc.LichHocId == schedule["lichHocId"]
    ).one()
    assert saved_schedule.NguoiHuyId == teacher.NguoiDungId
    assert saved_schedule.NgayHuy is not None
    history = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == schedule["lichHocId"],
        LichHocLichSu.HanhDong == "Hủy"
    ).one()
    assert history.NguoiThucHienId == teacher.NguoiDungId
    assert history.ThoiDiem == saved_schedule.NgayHuy
    assert history.LyDo == "Giảng viên bận"
    assert json.loads(history.DuLieuCu)["trangThai"] == "Đã lên lịch"
    assert json.loads(history.DuLieuMoi)["trangThai"] == "Đã hủy"

    with pytest.raises(HTTPException) as caught:
        cancel_schedule(
            schedule["lichHocId"],
            LichHocCancel(lyDo="Hủy lần nữa"),
            teacher,
            db,
        )
    assert caught.value.status_code == 409


def test_cancel_schedule_rejects_recorded_attendance_without_changes(
    db: Session,
):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 20, 2, "Học viên đã điểm danh")
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
    attendance = DiemDanh(
        LichHocId=schedule["lichHocId"],
        HocVienId=student.NguoiDungId,
        TrangThai="Có mặt",
        NguoiDiemDanhId=teacher.NguoiDungId,
        NgayCapNhat=datetime.now(),
    )
    db.add(attendance)
    db.commit()

    with pytest.raises(HTTPException) as caught:
        cancel_schedule(
            schedule["lichHocId"],
            LichHocCancel(lyDo="Giảng viên bận"),
            teacher,
            db,
        )

    assert caught.value.status_code == 409
    saved_schedule = db.query(LichHoc).filter(
        LichHoc.LichHocId == schedule["lichHocId"]
    ).one()
    assert saved_schedule.TrangThai == "Đã lên lịch"
    assert saved_schedule.LyDoHuy is None
    assert saved_schedule.NgayHuy is None
    assert saved_schedule.NguoiHuyId is None
    assert db.query(DiemDanh).filter(
        DiemDanh.LichHocId == schedule["lichHocId"]
    ).count() == 1
    history = db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == schedule["lichHocId"]
    ).all()
    assert [item.HanhDong for item in history] == ["Tạo"]


def test_schedule_change_notifies_affected_students_and_both_instructors(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    teacher, room, subject, class_record = setup_schedule_context(db)
    new_teacher = add_user(db, 4, 4, "Giảng viên thay thế")
    student = add_user(db, 20, 2, "Học viên trong lớp")
    old_day = date.today() + timedelta(days=18)
    db.add(
        LopHocHocVien(
            LopHocId=class_record.LopHocId,
            HocVienId=student.NguoiDungId,
            NgayThamGia=datetime.combine(old_day - timedelta(days=5), time.min),
            NguoiGhiDanhId=teacher.NguoiDungId,
        )
    )
    new_room = PhongHoc(
        PhongHocId=2,
        MaPhong="A102",
        TenPhong="Phòng A102",
        SucChua=30,
        TrangThai="Đang hoạt động",
    )
    db.add(new_room)
    db.commit()
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=old_day,
        ),
        teacher,
        db,
    )
    delivered = []
    monkeypatch.setattr(
        schedule_notifications,
        "send_schedule_change_email",
        lambda email, name, content: delivered.append((email, name, content)),
    )

    changed = update_schedule(
        schedule["lichHocId"],
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            new_room.PhongHocId,
            new_teacher.NguoiDungId,
            day=old_day + timedelta(days=1),
            start=time(11),
            end=time(12),
        ),
        teacher,
        db,
    )

    notifications = db.query(LichHocThongBao).all()
    assert changed["ngayHoc"] == (old_day + timedelta(days=1)).isoformat()
    assert {item.NguoiNhanId for item in notifications} == {
        teacher.NguoiDungId,
        new_teacher.NguoiDungId,
        student.NguoiDungId,
    }
    assert len({item.SuKienId for item in notifications}) == 1
    assert all(item.LoaiSuKien == "Thay đổi lịch" for item in notifications)
    assert all(item.TrangThai == "Đã gửi" for item in notifications)
    assert all(item.SoLanGui == 1 for item in notifications)
    assert all(
        item.NguoiThucHienId == teacher.NguoiDungId
        for item in notifications
    )
    assert all(item.ThoiDiemGui is not None for item in notifications)
    assert all(
        json.loads(item.DuLieuCu)["ngayHoc"] == old_day.isoformat()
        for item in notifications
    )
    assert all(
        json.loads(item.DuLieuMoi)["ngayHoc"]
        == (old_day + timedelta(days=1)).isoformat()
        for item in notifications
    )
    assert len(delivered) == 3


def test_cancel_schedule_notifies_enrolled_students_with_cancellation_reason(
    db: Session,
):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 20, 2, "Học viên trong lớp")
    day = date.today() + timedelta(days=18)
    db.add(
        LopHocHocVien(
            LopHocId=class_record.LopHocId,
            HocVienId=student.NguoiDungId,
            NgayThamGia=datetime.combine(day - timedelta(days=5), time.min),
            NguoiGhiDanhId=teacher.NguoiDungId,
        )
    )
    db.commit()
    schedule = create_schedule(
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

    cancel_schedule(
        schedule["lichHocId"],
        LichHocCancel(lyDo="Giảng viên đột xuất nghỉ."),
        teacher,
        db,
    )

    notifications = db.query(LichHocThongBao).all()
    assert {item.NguoiNhanId for item in notifications} == {
        teacher.NguoiDungId,
        student.NguoiDungId,
    }
    assert all(item.LoaiSuKien == "Hủy buổi học" for item in notifications)
    assert all(item.LyDo == "Giảng viên đột xuất nghỉ." for item in notifications)
    assert all(
        json.loads(item.DuLieuCu)["trangThai"] == "Đã lên lịch"
        for item in notifications
    )
    assert all(
        json.loads(item.DuLieuMoi)["trangThai"] == "Đã hủy"
        for item in notifications
    )
    assert all(
        "Giảng viên đột xuất nghỉ." in item.NoiDung
        for item in notifications
    )


def test_failed_schedule_notification_can_be_retried_without_duplicate_rows(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
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
    calls = []

    def fail_once(_email, _name, _content):
        calls.append(True)
        if len(calls) == 1:
            raise ValueError("SMTP temporarily unavailable")

    monkeypatch.setattr(
        schedule_notifications,
        "send_schedule_change_email",
        fail_once,
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

    notification = db.query(LichHocThongBao).one()
    notification_id = notification.LichHocThongBaoId
    assert changed["gioBatDau"] == "11:00"
    assert notification.TrangThai == "Thất bại"
    assert notification.SoLanGui == 1
    assert notification.LoiGui == "SMTP temporarily unavailable"
    assert db.query(LichHoc).filter(
        LichHoc.LichHocId == schedule["lichHocId"]
    ).one().GioBatDau == time(11)

    result = schedule_notifications.process_schedule_notifications(
        db,
        retry_failed=True,
    )

    retried = db.query(LichHocThongBao).one()
    assert result == {"processed": 1, "sent": 1, "failed": 0}
    assert retried.LichHocThongBaoId == notification_id
    assert retried.TrangThai == "Đã gửi"
    assert retried.SoLanGui == 2
    assert retried.LoiGui is None
    assert db.query(LichHocThongBao).count() == 1
    assert schedule_notifications.process_schedule_notifications(
        db,
        retry_failed=True,
    ) == {"processed": 0, "sent": 0, "failed": 0}


def test_schedule_notification_retries_stop_at_the_configured_limit(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
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
    attempts = []

    def always_fail(_email, _name, _content):
        attempts.append(True)
        raise RuntimeError("SMTP unavailable")

    monkeypatch.setattr(
        schedule_notifications,
        "send_schedule_change_email",
        always_fail,
    )
    update_schedule(
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
    for _ in range(2):
        result = schedule_notifications.process_schedule_notifications(
            db,
            retry_failed=True,
        )
        assert result == {"processed": 1, "sent": 0, "failed": 1}

    assert schedule_notifications.process_schedule_notifications(
        db,
        retry_failed=True,
    ) == {"processed": 0, "sent": 0, "failed": 0}
    notification = db.query(LichHocThongBao).one()
    assert notification.TrangThai == "Thất bại"
    assert notification.SoLanGui == 3
    assert len(attempts) == 3


def test_schedule_notification_is_not_created_for_no_op_update(db: Session):
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

    update_schedule(
        schedule["lichHocId"],
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
        ),
        teacher,
        db,
    )

    assert db.query(LichHocThongBao).count() == 0


def test_schedule_update_defers_notification_delivery_until_background_task(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
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
    delivered_event_ids = []
    monkeypatch.setattr(
        schedules_router,
        "_deliver_schedule_notifications",
        delivered_event_ids.append,
    )
    background_tasks = BackgroundTasks()

    changed = schedules_router.update_schedule_route(
        schedule["lichHocId"],
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            start=time(11),
            end=time(12),
        ),
        background_tasks,
        teacher,
        db,
    )

    assert changed["gioBatDau"] == "11:00"
    assert db.query(LichHocLichSu).filter(
        LichHocLichSu.LichHocId == schedule["lichHocId"],
        LichHocLichSu.HanhDong == "Cập nhật",
    ).count() == 1
    assert delivered_event_ids == []
    assert len(background_tasks.tasks) == 1

    asyncio.run(background_tasks())

    assert len(delivered_event_ids) == 1


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
    assert schedule["trangThaiDiemDanh"] == "Không có học viên"

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
    assert schedules[0]["trangThaiDiemDanh"] == "Không có học viên"
    assert options["diemDanhDuocHoTro"] is True


def test_completed_schedules_are_separate_and_paginated(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    now = business_time.business_now_naive()
    completed_rows = [
        LichHoc(
            LopHocId=class_record.LopHocId,
            MonHocId=subject.MonHocId,
            NgayHoc=now.date() - timedelta(days=days_ago),
            GioBatDau=time(9),
            GioKetThuc=time(10),
            PhongHocId=room.PhongHocId,
            GiangVienId=teacher.NguoiDungId,
            TrangThai="Đã lên lịch",
            NgayTao=now,
            NguoiTaoId=teacher.NguoiDungId,
            NgayCapNhat=now,
            NguoiCapNhatId=teacher.NguoiDungId,
        )
        for days_ago in (1, 2)
    ]
    db.add_all(completed_rows)
    db.commit()

    current_schedules = list_schedules(
        None,
        None,
        None,
        teacher,
        db,
        exclude_completed=True,
    )
    first_page = list_completed_schedules(
        page=1,
        page_size=1,
        current_user=teacher,
        db=db,
    )
    second_page = list_completed_schedules(
        page=2,
        page_size=1,
        current_user=teacher,
        db=db,
    )

    assert current_schedules == []
    assert first_page["total"] == 2
    assert first_page["page"] == 1
    assert first_page["pageSize"] == 1
    assert len(first_page["items"]) == len(second_page["items"]) == 1
    assert first_page["items"][0]["trangThai"] == "Đã diễn ra"
    assert first_page["items"][0]["lichHocId"] != second_page["items"][0]["lichHocId"]


def test_student_completed_history_includes_past_assigned_inactive_classes(
    db: Session,
):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 20, 2, "Học viên xem lịch sử")
    class_record.TrangThai = "Đã kết thúc"
    past_day = business_time.business_now().date() - timedelta(days=1)
    db.add_all(
        [
            LopHocHocVien(
                LopHocId=class_record.LopHocId,
                HocVienId=student.NguoiDungId,
                NgayThamGia=datetime.combine(past_day, time.min),
                NguoiGhiDanhId=teacher.NguoiDungId,
            ),
            LichHoc(
                LopHocId=class_record.LopHocId,
                MonHocId=subject.MonHocId,
                NgayHoc=past_day,
                GioBatDau=time(9),
                GioKetThuc=time(10),
                PhongHocId=room.PhongHocId,
                GiangVienId=teacher.NguoiDungId,
                TrangThai="Đã lên lịch",
                NgayTao=datetime.now(),
                NguoiTaoId=teacher.NguoiDungId,
                NgayCapNhat=datetime.now(),
                NguoiCapNhatId=teacher.NguoiDungId,
            ),
        ]
    )
    db.commit()

    result = list_completed_schedules(
        page=1,
        page_size=20,
        current_user=student,
        db=db,
    )

    assert result["total"] == 1
    assert result["items"][0]["maLop"] == class_record.MaLop
    assert result["items"][0]["trangThai"] == "Đã diễn ra"


def test_student_schedule_list_is_limited_to_enrolled_classes(db: Session):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 20, 2, "Học viên xem lịch")
    second_class = LopHoc(
        MaLop="CS101-02",
        TenLop="Lớp Lập trình khác",
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
    db.add(second_class)
    db.flush()
    db.add_all(
        [
            LopHocMonHoc(
                LopHocId=second_class.LopHocId,
                MonHocId=subject.MonHocId,
            ),
            LopHocHocVien(
                LopHocId=class_record.LopHocId,
                HocVienId=student.NguoiDungId,
                NgayThamGia=datetime.now(),
            ),
        ]
    )
    db.commit()

    enrolled_schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
        ),
        teacher,
        db,
    )
    create_schedule(
        schedule_request(
            second_class.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=business_time.business_now().date() + timedelta(days=11),
            start=time(11),
            end=time(12),
        ),
        teacher,
        db,
    )
    create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=business_time.business_now().date() + timedelta(days=13),
            start=time(13),
            end=time(14),
        ),
        teacher,
        db,
    )
    db.add(
        StudentEnrollmentAction(
            HocVienId=student.NguoiDungId,
            LopHocId=class_record.LopHocId,
            LopHocDichId=None,
            LoaiThaoTac="ThoiHoc",
            NgayHieuLuc=(
                business_time.business_now().date() + timedelta(days=12)
            ),
            LyDo="Ngừng học trước buổi kế tiếp",
            NguoiThucHienId=teacher.NguoiDungId,
            NgayTao=datetime.now(),
        )
    )
    db.commit()

    schedules = list_schedules(None, None, None, student, db)

    assert [item["lichHocId"] for item in schedules] == [
        enrolled_schedule["lichHocId"]
    ]


def test_attendance_persists_status_and_uses_session_date_roster(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    teacher, room, subject, class_record = setup_schedule_context(db)
    first_student = add_user(db, 20, 2, "Học viên được điểm danh")
    withdrawn_student = add_user(db, 21, 2, "Học viên đã thôi học")
    session_day = date.today() - timedelta(days=2)
    monkeypatch.setattr(
        schedules_router,
        "business_now_naive",
        lambda: datetime.combine(session_day, time(9, 30)),
    )
    db.add_all(
        [
            LopHocHocVien(
                LopHocId=class_record.LopHocId,
                HocVienId=student.NguoiDungId,
                NgayThamGia=datetime.combine(
                    session_day - timedelta(days=1), time.min
                ),
                NguoiGhiDanhId=teacher.NguoiDungId,
            )
            for student in (first_student, withdrawn_student)
        ]
    )
    db.add(
        StudentEnrollmentAction(
            HocVienId=withdrawn_student.NguoiDungId,
            LopHocId=class_record.LopHocId,
            LopHocDichId=None,
            LoaiThaoTac="ThoiHoc",
            NgayHieuLuc=session_day,
            LyDo="Đã thôi học trước buổi này",
            NguoiThucHienId=teacher.NguoiDungId,
            NgayTao=datetime.now(),
        )
    )
    db.commit()
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=session_day,
        ),
        teacher,
        db,
    )

    roster = get_schedule_attendance(schedule["lichHocId"], teacher, db)
    lock_calls = []
    monkeypatch.setattr(
        schedules_router,
        "_acquire_schedule_write_lock",
        lambda session: lock_calls.append(session),
    )
    saved = update_schedule_attendance(
        schedule["lichHocId"],
        DiemDanhWrite(
            hocViens=[
                {
                    "hocVienId": first_student.NguoiDungId,
                    "trangThai": "Đi muộn",
                    "ghiChu": "Đến sau giờ bắt đầu",
                }
            ]
        ),
        teacher,
        db,
    )
    queried = get_schedule_attendance(schedule["lichHocId"], teacher, db)

    assert [item["hocVienId"] for item in roster["hocViens"]] == [
        first_student.NguoiDungId
    ]
    assert saved["trangThaiDiemDanh"] == "1/1 đã điểm danh"
    assert queried["hocViens"][0]["trangThai"] == "Đi muộn"
    assert queried["hocViens"][0]["ghiChu"] == "Đến sau giờ bắt đầu"
    assert queried["hocViens"][0]["nguoiDiemDanh"] == teacher.HoTen
    assert db.query(DiemDanh).count() == 1
    assert db.query(AttendanceAudit).count() == 1
    assert lock_calls == [db]

    with pytest.raises(HTTPException) as error:
        update_schedule_attendance(
            schedule["lichHocId"],
            DiemDanhWrite(
                hocViens=[
                    {
                        "hocVienId": withdrawn_student.NguoiDungId,
                        "trangThai": "Vắng không phép",
                    }
                ]
            ),
            teacher,
            db,
        )
    assert error.value.status_code == 422


def test_absence_request_approval_updates_attendance_and_notifies_student(
    db: Session,
):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 20, 2, "Học viên xin phép")
    manager = add_user(db, 21, 7, "Quản lý đào tạo")
    db.add(
        LopHocHocVien(
            LopHocId=class_record.LopHocId,
            HocVienId=student.NguoiDungId,
            NgayThamGia=datetime.now(),
            NguoiGhiDanhId=teacher.NguoiDungId,
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

    created = create_absence_request_service(
        AbsenceRequestWrite(
            scheduleId=schedule["lichHocId"],
            reason="Có lịch khám bệnh đã hẹn trước.",
        ),
        student,
        db,
    )
    assert created["status"] == "pending"
    assert created["studentName"] == student.HoTen

    with pytest.raises(HTTPException) as duplicate:
        create_absence_request_service(
            AbsenceRequestWrite(
                scheduleId=schedule["lichHocId"],
                reason="Gửi lại đơn.",
            ),
            student,
            db,
        )
    assert duplicate.value.status_code == 409

    reviewed = decide_absence_request(
        created["requestId"],
        AbsenceRequestDecision(
            decision="approved",
            reason="Đã nhận minh chứng.",
        ),
        manager,
        db,
    )
    assert reviewed["status"] == "approved"
    attendance = db.query(DiemDanh).one()
    assert attendance.TrangThai == "Vắng có phép"
    assert db.query(AttendanceAudit).one().TrangThaiMoi == "Vắng có phép"
    notification = db.query(AttendanceNotification).one()
    assert notification.NguoiNhanId == student.NguoiDungId
    assert "được duyệt" in notification.NoiDung


def test_teacher_cannot_edit_attendance_after_session_ended(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    teacher, room, subject, class_record = setup_schedule_context(db)
    student = add_user(db, 20, 2, "Học viên")
    session_day = business_time.business_now().date() - timedelta(days=1)
    db.add(
        LopHocHocVien(
            LopHocId=class_record.LopHocId,
            HocVienId=student.NguoiDungId,
            NgayThamGia=datetime.combine(session_day - timedelta(days=2), time.min),
            NguoiGhiDanhId=teacher.NguoiDungId,
        )
    )
    db.commit()
    schedule = create_schedule(
        schedule_request(
            class_record.LopHocId,
            subject.MonHocId,
            room.PhongHocId,
            teacher.NguoiDungId,
            day=session_day,
        ),
        teacher,
        db,
    )
    monkeypatch.setattr(
        schedules_router,
        "business_now_naive",
        lambda: datetime.combine(session_day, time(11)),
    )

    with pytest.raises(HTTPException) as caught:
        update_schedule_attendance(
            schedule["lichHocId"],
            DiemDanhWrite(
                hocViens=[
                    {
                        "hocVienId": student.NguoiDungId,
                        "trangThai": "Vắng không phép",
                    }
                ]
            ),
            teacher,
            db,
        )
    assert caught.value.status_code == 403
    assert db.query(DiemDanh).count() == 0
