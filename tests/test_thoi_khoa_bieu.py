import pytest
from datetime import date, time
from fastapi.testclient import TestClient
from fastapi import HTTPException
from pydantic import ValidationError
from types import SimpleNamespace

from app.main import app
from app.routers.thoi_khoa_bieu import update_thoi_khoa_bieu
from app.schemas.thoi_khoa_bieu import ThoiKhoaBieuUpdate


class QueryResult:
    def __init__(self, result):
        self.result = result

    def filter(self, *_args):
        return self

    def first(self):
        return self.result


class FakeSession:
    def __init__(self, lesson, attendance=None):
        self.results = iter((lesson, attendance))
        self.added = []
        self.committed = False

    def query(self, *_args):
        return QueryResult(next(self.results))

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True

    def refresh(self, _item):
        pass

client = TestClient(app)

def test_xem_truoc_thoi_khoa_bieu_unauthorized():
    # Kiểm tra API xem trước khi chưa truyền thông tin hợp lệ / không có token
    response = client.post("/thoi-khoa-bieu/xem-truoc", json={})
    assert response.status_code in [401, 403, 422]

def test_gan_bai_hoc_not_found():
    # Kiểm tra gắn bài học cho buổi học không tồn tại
    response = client.put(
        "/thoi-khoa-bieu/999999/gan-bai-hoc",
        json={"bai_hoc_id": 1, "noi_dung_bai_hoc": "Bài 1: Tổng quan"}
    )
    assert response.status_code in [401, 403, 404]


def make_lesson():
    return SimpleNamespace(
        ThoiKhoaBieuId=12,
        LopHocId=3,
        MonHocId=4,
        GiangVienId=5,
        PhongHocId=6,
        NgayHoc=date(2030, 5, 20),
        GioBatDau=time(9, 0),
        GioKetThuc=time(10, 0),
        TrangThai="Lên lịch",
        NgayCapNhat=None,
        NguoiCapNhatId=None,
    )


def test_update_schedule_writes_audit_snapshot():
    lesson = make_lesson()
    db = FakeSession(lesson)
    current_user = SimpleNamespace(NguoiDungId=7)

    response = update_thoi_khoa_bieu(
        12,
        ThoiKhoaBieuUpdate(gioBatDau="10:00", gioKetThuc="11:00"),
        db,
        current_user,
    )

    assert response["gioBatDau"] == time(10, 0)
    assert lesson.GioBatDau == time(10, 0)
    assert lesson.NguoiCapNhatId == 7
    assert db.committed
    assert db.added[0].HanhDong == "Cập nhật"
    assert '"gioBatDau": "09:00:00"' in db.added[0].DuLieuCu
    assert '"gioBatDau": "10:00:00"' in db.added[0].DuLieuMoi


def test_update_schedule_rejected_when_attendance_exists():
    db = FakeSession(make_lesson(), attendance=object())
    current_user = SimpleNamespace(NguoiDungId=7)

    with pytest.raises(HTTPException) as error:
        update_thoi_khoa_bieu(
            12,
            ThoiKhoaBieuUpdate(ngayHoc="2030-05-21"),
            db,
            current_user,
        )

    assert error.value.status_code == 409
    assert not db.committed


def test_update_schedule_requires_end_after_start():
    db = FakeSession(make_lesson())
    current_user = SimpleNamespace(NguoiDungId=7)

    with pytest.raises(HTTPException) as error:
        update_thoi_khoa_bieu(
            12,
            ThoiKhoaBieuUpdate(gioKetThuc="08:30"),
            db,
            current_user,
        )

    assert error.value.status_code == 422
    assert not db.committed


def test_update_schedule_rejects_timezone_aware_local_time():
    with pytest.raises(ValidationError):
        ThoiKhoaBieuUpdate(gioBatDau="10:00:00+07:00")
def test_loc_thoi_khoa_bieu_unauthorized():
    # Kiểm tra API lọc thời khóa biểu khi chưa truyền Token xác thực
    response = client.get("/thoi-khoa-bieu/loc-lich?ngay=2026-10-20")
    assert response.status_code in [401, 403]