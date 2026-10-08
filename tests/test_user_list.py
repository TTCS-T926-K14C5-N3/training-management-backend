from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.vai_tro import VaiTro
from app.routers.nguoi_dung import get_users


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


def test_user_list_includes_all_assigned_role_names(db):
    user = NguoiDung(
        NguoiDungId=1,
        HoTen="Người dùng kiểm thử",
        Email="user@example.com",
        MatKhauHash="not-a-real-password-hash",
        TrangThai="HoatDong",
    )
    roles = [
        VaiTro(VaiTroId=2, TenVaiTro="Học viên"),
        VaiTro(VaiTroId=3, TenVaiTro="Giảng viên"),
    ]
    db.add_all([user, *roles])
    db.flush()
    db.add_all(
        [
            NguoiDungVaiTro(
                NguoiDungId=1,
                VaiTroId=2,
                NgayGan=datetime.now(),
            ),
            NguoiDungVaiTro(
                NguoiDungId=1,
                VaiTroId=3,
                NgayGan=datetime.now(),
            ),
        ]
    )
    db.commit()

    result = get_users(
        search=None,
        role_id=None,
        status=None,
        page=1,
        limit=20,
        db=db,
    )

    assert result["data"][0]["vaiTro"] == "Học viên, Giảng viên"


def test_user_list_shows_newest_users_first(db):
    users = [
        NguoiDung(
            NguoiDungId=user_id,
            HoTen=f"Người dùng {user_id}",
            Email=f"user{user_id}@example.com",
            MatKhauHash="not-a-real-password-hash",
            TrangThai="HoatDong",
        )
        for user_id in (1, 2)
    ]
    db.add_all(users)
    db.commit()

    result = get_users(
        search=None,
        role_id=None,
        status=None,
        page=1,
        limit=1,
        db=db,
    )

    assert [user["nguoiDungId"] for user in result["data"]] == [2]
