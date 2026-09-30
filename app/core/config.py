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