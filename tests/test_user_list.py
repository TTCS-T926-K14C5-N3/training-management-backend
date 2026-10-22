from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.vai_tro import VaiTro
from app.models.admissions import Lead, LeadConversion
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
    assert result["data"][0]["vaiTroIds"] == [2, 3]


def test_user_search_matches_student_code_and_numeric_user_id(db):
    student = NguoiDung(
        NguoiDungId=21,
        HoTen="Học viên tra cứu",
        Email="student@example.com",
        SoDienThoai="0912345678",
        MatKhauHash="not-a-real-password-hash",
        TrangThai="HoatDong",
    )
    db.add_all(
        [
            student,
            VaiTro(VaiTroId=2, TenVaiTro="Học viên"),
        ]
    )
    db.flush()
    db.add_all(
        [
            NguoiDungVaiTro(
                NguoiDungId=student.NguoiDungId,
                VaiTroId=2,
                NgayGan=datetime.now(),
            ),
            Lead(
                LeadId=1,
                HoTen=student.HoTen,
                SoDienThoai=student.SoDienThoai,
                Nguon="Kiểm thử",
                TrangThai="Đã nhập học",
                NgayTao=datetime.now(),
                NgayCapNhat=datetime.now(),
            ),
        ]
    )
    db.flush()
    db.add(
        LeadConversion(
            LeadId=1,
            NguoiDungId=student.NguoiDungId,
            MaHocVien="HV000021",
            NgayNhapHoc=datetime.now(),
            NguoiChuyenDoiId=student.NguoiDungId,
        )
    )
    db.commit()

    code_result = get_users(
        search="HV000021",
        role_id=2,
        status=None,
        page=1,
        limit=20,
        db=db,
    )
    id_result = get_users(
        search="21",
        role_id=2,
        status=None,
        page=1,
        limit=20,
        db=db,
    )

    assert [item["maHocVien"] for item in code_result["data"]] == ["HV000021"]
    assert [item["nguoiDungId"] for item in id_result["data"]] == [21]
