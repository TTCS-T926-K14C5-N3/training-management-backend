import smtplib
from email.message import EmailMessage

from app.core.config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    SMTP_FROM,
    ADMIN_CONTACT_PHONE,
    ADMIN_CONTACT_EMAIL,
)


# ============================================================
# GỬI EMAIL QUA SMTP
# ============================================================

def _send_email(
    message: EmailMessage,
    error_label: str,
):
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise RuntimeError(
            "Chưa cấu hình SMTP_USERNAME hoặc SMTP_PASSWORD"
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
            f"{error_label}: {exc}"
        ) from exc


# ============================================================
# GỬI EMAIL ĐẶT LẠI MẬT KHẨU
# ============================================================

def send_reset_password_email(
    recipient_email: str,
    reset_link: str,
):
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

Thông tin liên hệ quản trị viên:
Số điện thoại: {ADMIN_CONTACT_PHONE}
Email: {ADMIN_CONTACT_EMAIL}
"""
    )

    _send_email(
        message,
        "Không thể gửi email đặt lại mật khẩu",
    )


# ============================================================
# GỬI EMAIL KÍCH HOẠT TÀI KHOẢN
# ============================================================

def send_activation_email(
    recipient_email: str,
    ho_ten: str,
    temporary_password: str,
    activation_link: str,
    ma_hoc_vien: str | None = None,
):
    message = EmailMessage()

    message["Subject"] = (
        "Thông tin tài khoản - Hệ thống quản lý đào tạo"
    )

    message["From"] = SMTP_FROM
    message["To"] = recipient_email

    message.set_content(
        f"""Xin chào {ho_ten},

Quản trị viên đã tạo tài khoản cho bạn
trên Hệ thống quản lý đào tạo.

THÔNG TIN ĐĂNG NHẬP
-------------------------
Email: {recipient_email}
Mật khẩu tạm thời: {temporary_password}
{f"Mã học viên: {ma_hoc_vien}" if ma_hoc_vien else ""}

KÍCH HOẠT TÀI KHOẢN
-------------------------
Vui lòng nhấn vào liên kết dưới đây:

{activation_link}

Sau khi kích hoạt, bạn sẽ được chuyển đến
trang đăng nhập của hệ thống.

Hãy sử dụng Email và mật khẩu tạm thời ở trên
để đăng nhập.

Sau lần đăng nhập đầu tiên, hệ thống sẽ yêu cầu
bạn đổi sang mật khẩu mới.

Nếu bạn không yêu cầu tạo tài khoản này,
vui lòng liên hệ quản trị viên.

Trân trọng,
Hệ thống quản lý đào tạo

Thông tin liên hệ quản trị viên:
Số điện thoại: {ADMIN_CONTACT_PHONE}
Email: {ADMIN_CONTACT_EMAIL}
"""
    )

    _send_email(
        message,
        "Không thể gửi email tạo tài khoản",
    )