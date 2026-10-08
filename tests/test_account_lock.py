from datetime import datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, verify_access_token
from app.database import Base
from app.models.nguoi_dung import NguoiDung
from app.schemas.login import LoginRequest
from app.schemas.nguoi_dung import NguoiDungLock
from app.services.auth_service import login_user, lock_user, unlock_user


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def make_user(db) -> NguoiDung:
    user = NguoiDung(
        NguoiDungId=1,
        HoTen="Tài khoản kiểm thử",
        Email="locked@example.com",
        MatKhauHash="not-a-real-password-hash",
        TrangThai="HoatDong",
        DaKichHoat=True,
        BatBuocDoiMatKhau=False,
        CanDoiMatKhau=False,
        NgayTao=datetime.now(),
    )
    db.add(user)
    db.commit()
    return user


def test_lock_reason_is_required_and_stripped():
    with pytest.raises(ValidationError):
        NguoiDungLock.model_validate({})

    with pytest.raises(ValidationError):
        NguoiDungLock.model_validate({"lyDoKhoa": "   "})

    assert NguoiDungLock.model_validate(
        {"lyDoKhoa": "  Vi phạm quy định  "}
    ).ly_do_khoa == "Vi phạm quy định"


def test_lock_revokes_open_token_and_unlock_does_not_restore_it(db):
    user = make_user(db)
    token = create_access_token(
        {"sub": user.Email, "user_id": user.NguoiDungId}
    )

    assert verify_access_token(token, db) == user

    lock_user(
        db,
        user.NguoiDungId,
        NguoiDungLock(ly_do_khoa="Vi phạm quy định"),
    )
    assert user.LyDoKhoa == "Vi phạm quy định"

    with pytest.raises(HTTPException) as locked_error:
        verify_access_token(token, db)
    assert locked_error.value.status_code == 401
    assert "đã bị khóa" in locked_error.value.detail

    with pytest.raises(HTTPException) as login_error:
        login_user(
            db,
            LoginRequest(email=user.Email, password="password"),
        )
    assert login_error.value.status_code == 423
    assert "Vi phạm quy định" in login_error.value.detail

    unlock_user(db, user.NguoiDungId)

    with pytest.raises(HTTPException) as revoked_error:
        verify_access_token(token, db)
    assert revoked_error.value.status_code == 401
    assert "đã bị thu hồi" in revoked_error.value.detail

    fresh_token = create_access_token(
        {"sub": user.Email, "user_id": user.NguoiDungId}
    )
    assert verify_access_token(fresh_token, db) == user
