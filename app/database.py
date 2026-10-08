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


def _quote_odbc_value(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


connection_string = (
    f"DRIVER={{{DB_DRIVER}}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"Trusted_Connection={'yes' if DB_TRUSTED_CONNECTION else 'no'};"
    f"TrustServerCertificate="
    f"{'yes' if DB_TRUST_SERVER_CERTIFICATE else 'no'};"
)

if not DB_TRUSTED_CONNECTION:
    assert DB_USER is not None and DB_PASSWORD is not None
    connection_string += (
        f"UID={_quote_odbc_value(DB_USER)};"
        f"PWD={_quote_odbc_value(DB_PASSWORD)};"
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