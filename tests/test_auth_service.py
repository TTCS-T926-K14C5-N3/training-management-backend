from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import Unicode

from app.schemas.login import LoginRequest
from app.models.nguoi_dung import NguoiDung
from app.services import auth_service


class FakeQuery:
    def __init__(self, user):
        self.user = user

    def filter(self, _condition):
        return self

    def first(self):
        return self.user


class FakeSession:
    def __init__(self, user):
        self.user = user
        self.commit_count = 0
        self.added = []
        self.deleted = []

    def query(self, _model):
        return FakeQuery(self.user)

    def add(self, item):
        self.added.append(item)

    def delete(self, item):
        self.deleted.append(item)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        pass


def test_fifth_wrong_password_locks_account_for_15_minutes(monkeypatch):
    user = SimpleNamespace(
        Email="ntc@gmail.com",
        MatKhauHash="hashed-password",
        TrangThai="HoatDong",
        SoLanDangNhapSai=0,
        KhoaDen=None,
        LyDoKhoa=None,
    )
    db = FakeSession(user)
    monkeypatch.setattr(
        auth_service.password_hash,
        "verify",
        lambda _password, _hashed_password: False,
    )
    request = LoginRequest(
        email="ntc@gmail.com",
        password="wrong-password",
    )

    for attempt in range(1, 6):
        with pytest.raises(HTTPException) as error:
            auth_service.login_user(db, request)

        assert error.value.status_code == (423 if attempt == 5 else 401)

    assert user.SoLanDangNhapSai == 5
    assert user.TrangThai == "HoatDong"
    assert user.LyDoKhoa == "Sai mật khẩu 5 lần liên tiếp"
    assert user.KhoaDen is not None
    assert timedelta(minutes=14, seconds=59) < user.KhoaDen - datetime.now()
    assert user.KhoaDen - datetime.now() < timedelta(minutes=15, seconds=1)

    with pytest.raises(HTTPException) as error:
        auth_service.login_user(db, request)

    assert error.value.status_code == 423
    assert user.SoLanDangNhapSai == 5


def test_forgot_password_reports_mail_delivery_failure(monkeypatch):
    user = SimpleNamespace(
        NguoiDungId=17,
        Email="user@example.com",
    )
    db = FakeSession(user)

    def fail_to_send(**_kwargs):
        raise RuntimeError("SMTP authentication failed")

    monkeypatch.setattr(
        auth_service,
        "send_reset_password_email",
        fail_to_send,
    )

    with pytest.raises(HTTPException) as error:
        auth_service.forgot_password(
            db,
            auth_service.ForgotPasswordRequest(email=user.Email),
        )

    assert error.value.status_code == 503
    assert len(db.added) == 1
    assert db.deleted == db.added


def test_forgot_password_uses_configured_frontend_url(monkeypatch):
    user = SimpleNamespace(
        NguoiDungId=18,
        Email="user@example.com",
    )
    db = FakeSession(user)
    sent = {}
    monkeypatch.setattr(
        auth_service,
        "FRONTEND_URL",
        "https://training.example.com/",
    )
    monkeypatch.setattr(
        auth_service,
        "send_reset_password_email",
        lambda **kwargs: sent.update(kwargs),
    )

    response = auth_service.forgot_password(
        db,
        auth_service.ForgotPasswordRequest(email=user.Email),
    )

    assert response["message"]
    assert sent["reset_link"].startswith(
        "https://training.example.com/reset-password?token="
    )


def test_vietnamese_profile_fields_use_unicode_database_types():
    assert isinstance(NguoiDung.HoTen.type, Unicode)
    assert isinstance(NguoiDung.DiaChi.type, Unicode)
