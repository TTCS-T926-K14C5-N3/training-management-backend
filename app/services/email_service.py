import smtplib
from email.message import EmailMessage

from app.core.config import (
    ADMIN_CONTACT_EMAIL,
    ADMIN_CONTACT_PHONE,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USERNAME,
)


def _send_email(message: EmailMessage, error_label: str) -> None:
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise RuntimeError("Chưa cấu hình SMTP_USERNAME hoặc SMTP_PASSWORD")

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
    except Exception as exc:
        raise RuntimeError(f"{error_label}: {exc}") from exc


def send_reset_password_email(
    recipient_email: str,
    reset_link: str,
) -> None:
    message = EmailMessage()
    message["Subject"] = "Đặt lại mật khẩu - Hệ thống quản lý đào tạo"
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
    _send_email(message, "Không thể gửi email đặt lại mật khẩu")


def send_activation_email(
    recipient_email: str,
    ho_ten: str,
    temporary_password: str | None,
    activation_link: str,
    ma_hoc_vien: str | None = None,
) -> None:
    message = EmailMessage()
    message["Subject"] = "Thông tin tài khoản - Hệ thống quản lý đào tạo"
    message["From"] = SMTP_FROM
    message["To"] = recipient_email

    if temporary_password:
        account_details = (
            "THÔNG TIN ĐĂNG NHẬP\n"
            "-------------------------\n"
            f"Email: {recipient_email}\n"
            f"Mật khẩu tạm thời: {temporary_password}\n"
            + (f"Mã học viên: {ma_hoc_vien}\n" if ma_hoc_vien else "")
            + "\nSau khi đăng nhập, vui lòng đổi mật khẩu tạm thời.\n\n"
        )
        introduction = "Quản trị viên đã tạo tài khoản cho bạn.\n\n"
    else:
        account_details = ""
        introduction = "Bạn vừa yêu cầu gửi lại liên kết kích hoạt tài khoản.\n\n"

    message.set_content(
        f"""Xin chào {ho_ten},

{introduction}{account_details}Vui lòng nhấn vào liên kết dưới đây để kích hoạt tài khoản:

{activation_link}

Sau khi kích hoạt, bạn sẽ được chuyển đến trang đăng nhập.
Nếu bạn không yêu cầu thao tác này, vui lòng liên hệ quản trị viên.

Trân trọng,
Hệ thống quản lý đào tạo

Thông tin liên hệ quản trị viên:
Số điện thoại: {ADMIN_CONTACT_PHONE}
Email: {ADMIN_CONTACT_EMAIL}
"""
    )
    _send_email(message, "Không thể gửi email tạo tài khoản")


def send_schedule_change_email(
    recipient_email: str,
    ho_ten: str,
    notification_content: str,
) -> None:
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
    _send_email(message, "Không thể gửi email thông báo lịch học")


def send_absence_request_approved_email(
    recipient_email: str,
    ho_ten: str,
    class_label: str,
    subject_name: str,
    session_date: str,
    start_time: str,
    end_time: str,
    decision_reason: str,
) -> None:
    message = EmailMessage()
    message["Subject"] = "Đơn xin phép vắng đã được duyệt"
    message["From"] = SMTP_FROM
    message["To"] = recipient_email
    message.set_content(
        f"""Xin chào {ho_ten},

Đơn xin phép vắng của bạn đã được giảng viên duyệt.

Lớp: {class_label}
Môn học: {subject_name}
Thời gian: {session_date}, {start_time}–{end_time}
Lý do xử lý: {decision_reason}

Vui lòng đăng nhập hệ thống để theo dõi chi tiết đơn xin phép.

Trân trọng,
Hệ thống quản lý đào tạo
"""
    )
    _send_email(message, "Không thể gửi email kết quả đơn xin phép")
