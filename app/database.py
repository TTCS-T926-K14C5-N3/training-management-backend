from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker
)

from app.core.config import (
    DB_SERVER,
    DB_NAME,
    DB_DRIVER,
    DB_TRUSTED_CONNECTION,
    DB_TRUST_SERVER_CERTIFICATE,
    DB_USER,
    DB_PASSWORD,
)


def _odbc_value(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def build_connection_string(
    server: str,
    database: str,
    driver: str,
    trusted_connection: bool = True,
    trust_server_certificate: bool = True,
    username: str | None = None,
    password: str | None = None,
) -> str:
    parts = [
        f"DRIVER={_odbc_value(driver)}",
        f"SERVER={_odbc_value(server)}",
        f"DATABASE={_odbc_value(database)}",
        f"TrustServerCertificate={'yes' if trust_server_certificate else 'no'}",
    ]

    if trusted_connection:
        parts.append("Trusted_Connection=yes")
    else:
        if not username or not password:
            raise ValueError(
                "DB_TRUSTED_CONNECTION=no requires DB_USER and DB_PASSWORD."
            )
        parts.extend(
            [
                f"UID={_odbc_value(username)}",
                f"PWD={_odbc_value(password)}",
            ]
        )

    return ";".join(parts) + ";"


connection_string = build_connection_string(
    server=DB_SERVER,
    database=DB_NAME,
    driver=DB_DRIVER,
    trusted_connection=DB_TRUSTED_CONNECTION,
    trust_server_certificate=DB_TRUST_SERVER_CERTIFICATE,
    username=DB_USER,
    password=DB_PASSWORD,
)


DATABASE_URL = (
    "mssql+pyodbc:///?odbc_connect="
    + quote_plus(connection_string)
)


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


Base = declarative_base()


def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()