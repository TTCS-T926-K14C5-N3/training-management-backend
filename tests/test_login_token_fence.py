import contextlib
import io
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import verify_access_token
from app.database import Base
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.quyen import Quyen
from app.models.revoked_token import RevokedToken
from app.models.vai_tro import VaiTro
from app.models.vai_tro_quyen import VaiTroQuyen
from app.services import auth_service
from app.schemas.login import LoginRequest


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            NguoiDung.__table__,
            VaiTro.__table__,
            Quyen.__table__,
            NguoiDungVaiTro.__table__,
            VaiTroQuyen.__table__,
            RevokedToken.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_login_clamps_future_token_valid_after_and_accepts_new_token(
    db,
    monkeypatch,
):
    user = NguoiDung(
        HoTen="Người dùng kiểm thử",
        Email="login@example.com",
        MatKhauHash="test-hash",
        TrangThai="HoatDong",
        TokenValidAfter=datetime.now() + timedelta(hours=2),
    )
    db.add(user)
    db.commit()
    monkeypatch.setattr(
        auth_service.password_hash,
        "verify",
        lambda password, password_hash: (
            password == "correct-password"
            and password_hash == "test-hash"
        ),
    )

    response = auth_service.login_user(
        db,
        LoginRequest(email=user.Email, password="correct-password"),
    )

    db.refresh(user)
    assert user.TokenValidAfter is not None
    assert user.TokenValidAfter < datetime.now() + timedelta(seconds=1)

    with contextlib.redirect_stdout(io.StringIO()):
        verified_user = verify_access_token(
            response["access_token"],
            db,
        )

    assert verified_user.NguoiDungId == user.NguoiDungId
