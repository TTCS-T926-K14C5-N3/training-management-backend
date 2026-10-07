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