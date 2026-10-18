import smtplib
from email.message import EmailMessage

from app.core.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    SMTP_FROM,
)


# ============================================================
# GỬI EMAIL ĐẶT LẠI MẬT KHẨU
# ============================================================

def send_reset_password_email(
    recipient_email: str,
    reset_link: str,
):
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise RuntimeError(
            "Chưa cấu hình SMTP_USERNAME hoặc SMTP_PASSWORD"
        )

    message = EmailMessage()

    message["Subject"] = (
        "Đặt lại mật khẩu - Hệ thống quản lý đào tạo"
    )

    message["From"] = SMTP_FROM
    message["To"] = recipient_email

    message.set_content(
        f"""Xin chào,

Bạn vừa yêu cầu đặt lại mật khẩu cho tài khoản
trên Hệ thống quản lý đào tạo.

Vui lòng nhấn vào liên kết dưới đây để đặt lại mật khẩu:

{reset_link}

Liên kết này có hiệu lực trong 30 phút
và chỉ được sử dụng một lần.

Nếu bạn không yêu cầu đặt lại mật khẩu,
vui lòng bỏ qua email này.

Trân trọng,
Hệ thống quản lý đào tạo
"""
    )

    try:
        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=30,
        ) as server:

            server.ehlo()
            server.starttls()
            server.ehlo()

            server.login(
                SMTP_USERNAME,
                SMTP_PASSWORD,
            )

            server.send_message(message)

    except Exception as exc:
        raise RuntimeError(
            f"Không thể gửi email đặt lại mật khẩu: {exc}"
        ) from exc


# ============================================================
# GỬI EMAIL KÍCH HOẠT TÀI KHOẢN
# ============================================================

def send_activation_email(
    recipient_email: str,
    ho_ten: str,
    temporary_password: str | None,
    activation_link: str,
):
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise RuntimeError(
            "Chưa cấu hình SMTP_USERNAME hoặc SMTP_PASSWORD"
        )

    message = EmailMessage()

    message["Subject"] = (
        "Kích hoạt tài khoản - Hệ thống quản lý đào tạo"
    )

    message["From"] = SMTP_FROM
    message["To"] = recipient_email

    credentials = (
        f"Email: {recipient_email}\n"
        f"Mật khẩu tạm thời: {temporary_password}\n\n"
        "Sau khi kích hoạt, bạn có thể sử dụng email và mật khẩu tạm thời "
        "để đăng nhập. Vui lòng đổi mật khẩu sau lần đăng nhập đầu tiên.\n\n"
        if temporary_password
        else ""
    )
    introduction = (
        "Tài khoản của bạn đã được tạo trên Hệ thống quản lý đào tạo.\n\n"
        if temporary_password
        else "Bạn vừa yêu cầu gửi lại liên kết kích hoạt tài khoản.\n\n"
    )

    message.set_content(
        f"""Xin chào {ho_ten},

{introduction}{credentials}Vui lòng nhấn vào liên kết dưới đây để kích hoạt tài khoản:

{activation_link}

Nếu bạn không yêu cầu thao tác này, vui lòng bỏ qua email.

Trân trọng,
Hệ thống quản lý đào tạo
"""
    )

    try:
        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=30,
        ) as server:

            server.ehlo()
            server.starttls()
            server.ehlo()

            server.login(
                SMTP_USERNAME,
                SMTP_PASSWORD,
            )

            server.send_message(message)

    except Exception as exc:
        raise RuntimeError(
            f"Không thể gửi email kích hoạt tài khoản: {exc}"
        ) from exc


def send_schedule_change_email(
    recipient_email: str,
    ho_ten: str,
    notification_content: str,
):
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise RuntimeError(
            "Chưa cấu hình SMTP_USERNAME hoặc SMTP_PASSWORD"
        )

    message = EmailMessage()
    message["Subject"] = "Thông báo thay đổi lịch học"
    message["From"] = SMTP_FROM
    message["To"] = recipient_email
    message.set_content(
        f"""Xin chào {ho_ten},

{notification_content}

Vui lòng đăng nhập hệ thống để xem thông tin lịch học.
"""
    )

    try:
        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=30,
        ) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
    except Exception as exc:
        raise RuntimeError(
            f"Không thể gửi email thông báo lịch học: {exc}"
        ) from exc