import pytest

from app.database import build_connection_string


def test_build_connection_string_uses_windows_auth_by_default():
    connection_string = build_connection_string(
        server=r".\NVL",
        database="QuanLyDaoTao",
        driver="ODBC Driver 18 for SQL Server",
    )

    assert "SERVER={.\\NVL}" in connection_string
    assert "DATABASE={QuanLyDaoTao}" in connection_string
    assert "Trusted_Connection=yes" in connection_string
    assert "TrustServerCertificate=yes" in connection_string
    assert "UID=" not in connection_string
    assert "PWD=" not in connection_string


def test_build_connection_string_supports_sql_authentication():
    connection_string = build_connection_string(
        server="localhost",
        database="Training;Management",
        driver="ODBC Driver 18 for SQL Server",
        trusted_connection=False,
        trust_server_certificate=False,
        username="training-user",
        password="secret};value",
    )

    assert "DATABASE={Training;Management}" in connection_string
    assert "Trusted_Connection=" not in connection_string
    assert "TrustServerCertificate=no" in connection_string
    assert "UID={training-user}" in connection_string
    assert "PWD={secret}};value}" in connection_string


@pytest.mark.parametrize(
    ("username", "password"),
    [(None, None), ("training-user", None), (None, "secret")],
)
def test_sql_authentication_requires_username_and_password(username, password):
    with pytest.raises(ValueError, match="DB_USER and DB_PASSWORD"):
        build_connection_string(
            server="localhost",
            database="QuanLyDaoTao",
            driver="ODBC Driver 18 for SQL Server",
            trusted_connection=False,
            username=username,
            password=password,
        )
