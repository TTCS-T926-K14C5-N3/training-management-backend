from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import Unicode

from app.schemas.login import LoginRequest
from app.models.nguoi_dung import NguoiDung
from app.models.token_kich_hoat import TokenKichHoat
from app.schemas.resend_activation import ResendActivationRequest
from app.services import email_service
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


class ActivationQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model

    def filter(self, *_conditions):
        return self

    def first(self):
        return self.session.user

    def all(self):
        return self.session.tokens


class ActivationSession:
    def __init__(self, user, tokens=None):
        self.user = user
        self.tokens = tokens or []
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0

    def query(self, model):
        return ActivationQuery(self, model)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


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


def test_login_rejects_account_until_activation():
    user = SimpleNamespace(
        Email="user@example.com",
        DaKichHoat=False,
        TrangThai="HoatDong",
    )

    with pytest.raises(HTTPException) as error:
        auth_service.login_user(
            FakeSession(user),
            LoginRequest(email=user.Email, password="irrelevant"),
        )

    assert error.value.status_code == 403
    assert error.value.detail == "Tài khoản chưa được kích hoạt"


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


def test_resend_activation_rotates_expired_token_without_sending_password(
    monkeypatch,
):
    now = datetime.now()
    previous_token = TokenKichHoat(
        NguoiDungId=42,
        Token="old-hash",
        ThoiGianTao=now - timedelta(days=2),
        ThoiGianHetHan=now - timedelta(days=1),
        DaSuDung=False,
    )
    user = SimpleNamespace(
        NguoiDungId=42,
        Email="user@example.com",
        HoTen="Test User",
        DaKichHoat=False,
        TrangThai="HoatDong",
    )
    db = ActivationSession(user, [previous_token])
    sent = {}
    monkeypatch.setattr(
        auth_service,
        "FRONTEND_URL",
        "https://training.example.com/",
    )
    monkeypatch.setattr(
        auth_service,
        "send_activation_email",
        lambda **kwargs: sent.update(kwargs),
    )

    response = auth_service.resend_activation(
        db,
        ResendActivationRequest(email="USER@example.com"),
    )

    assert response["message"]
    assert previous_token.DaSuDung is True
    assert len(db.added) == 1
    new_token = db.added[0]
    assert isinstance(new_token, TokenKichHoat)
    assert new_token.DaSuDung is False
    assert new_token.ThoiGianHetHan > datetime.now()
    assert sent["temporary_password"] is None
    assert sent["activation_link"].startswith(
        "https://training.example.com/activate-account?token="
    )
    raw_token = sent["activation_link"].split("token=", maxsplit=1)[1]
    assert new_token.Token == auth_service.hashlib.sha256(
        raw_token.encode()
    ).hexdigest()
    assert db.commit_count == 1
    assert user.DaKichHoat is False


def test_resend_activation_uses_same_response_for_unknown_and_active_accounts(
    monkeypatch,
):
    monkeypatch.setattr(
        auth_service,
        "send_activation_email",
        lambda **_kwargs: pytest.fail("Email should not be sent"),
    )
    request = ResendActivationRequest(email="user@example.com")

    unknown_response = auth_service.resend_activation(
        ActivationSession(None),
        request,
    )
    active_response = auth_service.resend_activation(
        ActivationSession(
            SimpleNamespace(
                NguoiDungId=42,
                Email="user@example.com",
                HoTen="Test User",
                DaKichHoat=True,
                TrangThai="HoatDong",
            )
        ),
        request,
    )

    assert unknown_response == active_response


def test_resend_activation_does_not_send_within_cooldown(monkeypatch):
    now = datetime.now()
    recent_token = TokenKichHoat(
        NguoiDungId=42,
        Token="recent-hash",
        ThoiGianTao=now - timedelta(minutes=1),
        ThoiGianHetHan=now + timedelta(hours=1),
        DaSuDung=False,
    )
    user = SimpleNamespace(
        NguoiDungId=42,
        Email="user@example.com",
        HoTen="Test User",
        DaKichHoat=False,
        TrangThai="HoatDong",
    )
    db = ActivationSession(user, [recent_token])
    monkeypatch.setattr(
        auth_service,
        "send_activation_email",
        lambda **_kwargs: pytest.fail("Email should be rate limited"),
    )

    auth_service.resend_activation(
        db,
        ResendActivationRequest(email=user.Email),
    )

    assert db.added == []
    assert db.commit_count == 0


def test_resend_activation_invalidates_token_when_email_delivery_fails(
    monkeypatch,
):
    user = SimpleNamespace(
        NguoiDungId=42,
        Email="user@example.com",
        HoTen="Test User",
        DaKichHoat=False,
        TrangThai="HoatDong",
    )
    db = ActivationSession(user)
    monkeypatch.setattr(
        auth_service,
        "send_activation_email",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("SMTP unavailable")),
    )

    response = auth_service.resend_activation(
        db,
        ResendActivationRequest(email=user.Email),
    )

    assert response["message"]
    assert len(db.added) == 1
    assert db.added[0].DaSuDung is True
    assert db.commit_count == 2


def test_resend_activation_email_does_not_include_a_temporary_password(
    monkeypatch,
):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, *_args):
            pass

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(email_service, "SMTP_USERNAME", "smtp-user")
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", "smtp-password")
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)

    email_service.send_activation_email(
        recipient_email="user@example.com",
        ho_ten="Test User",
        temporary_password=None,
        activation_link="https://training.example.com/activate-account?token=secret",
    )

    body = sent_messages[0].get_content()
    assert "Mật khẩu tạm thời" not in body
    assert "https://training.example.com/activate-account?token=secret" in body


def test_schedule_change_email_matches_the_user_facing_notification(
    monkeypatch,
):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, *_args):
            pass

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(email_service, "SMTP_USERNAME", "smtp-user")
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", "smtp-password")
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)

    email_service.send_schedule_change_email(
        "recipient@example.com",
        "nvl",
        (
            "Buổi học BH-000002 đã thay đổi lịch. Trước: "
            "2026-10-18 08:00-10:00, phòng C4-104, "
            "giảng viên Nguyễn Văn User. Sau: "
            "2026-10-18 06:45-10:30, phòng C4-104, "
            "giảng viên Nguyễn Văn User."
        ),
    )

    assert sent_messages[0]["Subject"] == "Thông báo thay đổi lịch học"
    assert sent_messages[0].get_content() == (
        "Xin chào nvl,\n\n"
        "Buổi học BH-000002 đã thay đổi lịch. Trước: "
        "2026-10-18 08:00-10:00, phòng C4-104, "
        "giảng viên Nguyễn Văn User. Sau: "
        "2026-10-18 06:45-10:30, phòng C4-104, "
        "giảng viên Nguyễn Văn User.\n\n"
        "Vui lòng đăng nhập hệ thống để xem thông tin lịch học.\n"
    )


def test_vietnamese_profile_fields_use_unicode_database_types():
    assert isinstance(NguoiDung.HoTen.type, Unicode)
    assert isinstance(NguoiDung.DiaChi.type, Unicode)
