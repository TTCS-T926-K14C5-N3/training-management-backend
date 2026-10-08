import os

from dotenv import load_dotenv


load_dotenv()


DB_SERVER = os.getenv(
    "DB_SERVER"
)

DB_NAME = os.getenv(
    "DB_NAME",
    "QuanLyDaoTao"
)

DB_DRIVER = os.getenv(
    "DB_DRIVER",
    "ODBC Driver 18 for SQL Server"
)


if not DB_SERVER:
    raise ValueError(
        "Chua cau hinh DB_SERVER. "
        "Hay tao file .env tu .env.example."
    )

DB_TRUSTED_CONNECTION = os.getenv(
    "DB_TRUSTED_CONNECTION",
    "yes",
).strip().lower() in {"1", "true", "yes", "y"}

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_TRUSTED_CONNECTION and not (DB_USER and DB_PASSWORD):
    raise ValueError(
        "Can cau hinh DB_USER va DB_PASSWORD khi "
        "DB_TRUSTED_CONNECTION=no."
    )

DB_TRUST_SERVER_CERTIFICATE = os.getenv(
    "DB_TRUST_SERVER_CERTIFICATE",
    "yes",
).strip().lower() in {"1", "true", "yes", "y"}


# ============================================================
# SMTP - GỬI EMAIL
# ============================================================

SMTP_HOST = os.getenv(
    "SMTP_HOST",
    "smtp.gmail.com"
)

SMTP_PORT = int(
    os.getenv(
        "SMTP_PORT",
        "587"
    )
)

SMTP_USERNAME = os.getenv(
    "SMTP_USERNAME"
)

SMTP_PASSWORD = os.getenv(
    "SMTP_PASSWORD"
)

SMTP_FROM = os.getenv(
    "SMTP_FROM",
    SMTP_USERNAME
)

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173"
).rstrip("/")

CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

ADMIN_CONTACT_PHONE = os.getenv(
    "ADMIN_CONTACT_PHONE",
    "0912345678",
)

ADMIN_CONTACT_EMAIL = os.getenv(
    "ADMIN_CONTACT_EMAIL",
    "lyachai2k@gmail.com",
)