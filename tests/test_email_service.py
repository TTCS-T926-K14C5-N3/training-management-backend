from unittest.mock import MagicMock

import pytest

from app.services import email_service


def test_activation_and_reset_emails_include_admin_contact(monkeypatch):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    monkeypatch.setattr(email_service, "SMTP_USERNAME", "sender@example.com")
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", "smtp-password")
    monkeypatch.setattr(email_service, "ADMIN_CONTACT_PHONE", "0912345678")
    monkeypatch.setattr(
        email_service,
        "ADMIN_CONTACT_EMAIL",
        "lyachai2k@gmail.com",
    )
    monkeypatch.setattr(
        email_service.smtplib,
        "SMTP",
        MagicMock(return_value=smtp),
    )

    email_service.send_activation_email(
        recipient_email="user@example.com",
        ho_ten="Người dùng kiểm thử",
        temporary_password="temporary-password",
        activation_link="https://example.com/activate",
    )
    email_service.send_reset_password_email(
        recipient_email="user@example.com",
        reset_link="https://example.com/reset",
    )

    messages = [
        call.args[0]
        for call in smtp.send_message.call_args_list
    ]
    assert len(messages) == 2
    for message in messages:
        body = message.get_content()
        assert "Số điện thoại: 0912345678" in body
        assert "Email: lyachai2k@gmail.com" in body


def test_schedule_change_email_uses_configured_smtp(monkeypatch):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    monkeypatch.setattr(email_service, "SMTP_USERNAME", "sender@example.com")
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", "smtp-password")
    monkeypatch.setattr(
        email_service.smtplib,
        "SMTP",
        MagicMock(return_value=smtp),
    )

    email_service.send_schedule_change_email(
        "student@example.com",
        "Học viên",
        "Buổi học đã đổi lịch.",
    )

    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "student@example.com"
    assert message["Subject"] == "Thông báo thay đổi lịch học"
    assert "Buổi học đã đổi lịch." in message.get_content()


def test_schedule_change_email_surfaces_smtp_failures(monkeypatch):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.side_effect = OSError("connection failed")
    monkeypatch.setattr(email_service, "SMTP_USERNAME", "sender@example.com")
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", "smtp-password")
    monkeypatch.setattr(
        email_service.smtplib,
        "SMTP",
        MagicMock(return_value=smtp),
    )

    with pytest.raises(
        RuntimeError,
        match="Không thể gửi email thay đổi lịch học",
    ):
        email_service.send_schedule_change_email(
            "student@example.com",
            "Học viên",
            "Buổi học đã đổi lịch.",
        )
