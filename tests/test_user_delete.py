from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.diem import Diem
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.vai_tro import VaiTro
from app.services.auth_service import delete_user


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute(
            "PRAGMA foreign_keys=ON"
        ),
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.execute(
        text("""
            CREATE TABLE PhienDangNhap (
                PhienId INTEGER PRIMARY KEY,
                NguoiDungId INTEGER NOT NULL
                    REFERENCES NguoiDung(NguoiDungId),
                Token VARCHAR(500) NOT NULL,
                ThoiGianHetHan DATETIME NOT NULL
            )
        """)
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def add_user(db, user_id: int, email: str) -> NguoiDung:
    user = NguoiDung(
        NguoiDungId=user_id,
        HoTen="Người dùng kiểm thử",
        Email=email,
        MatKhauHash="not-a-real-password-hash",
        TrangThai="HoatDong",
    )
    db.add(user)
    db.commit()
    return user


def test_delete_user_cleans_account_links_and_detaches_academic_relations(db):
    user = add_user(db, 1, "student@example.com")
    role = VaiTro(VaiTroId=2, TenVaiTro="Sinh viên")
    db.add(role)
    db.flush()
    db.add(
        NguoiDungVaiTro(
            NguoiDungId=user.NguoiDungId,
            VaiTroId=role.VaiTroId,
            NgayGan=datetime.now(),
        )
    )
    class_record = LopHoc(
        MaLop="TEST-01",
        TenLop="Lớp kiểm thử",
        NamHoc="2026-2027",
        GiangVienId=user.NguoiDungId,
        NgayTao=datetime.now(),
    )
    db.add(class_record)
    db.flush()
    db.add(
        LopHocHocVien(
            LopHocId=class_record.LopHocId,
            HocVienId=user.NguoiDungId,
            NgayThamGia=datetime.now(),
        )
    )
    db.execute(
        text("""
            INSERT INTO PhienDangNhap
                (PhienId, NguoiDungId, Token, ThoiGianHetHan)
            VALUES
                (1, :user_id, 'session-token', :expires_at)
        """),
        {
            "user_id": user.NguoiDungId,
            "expires_at": datetime.now() + timedelta(days=1),
        },
    )
    db.commit()

    result = delete_user(db, user.NguoiDungId)

    assert result["message"] == "Xóa tài khoản thành công"
    assert db.get(NguoiDung, user.NguoiDungId) is None
    assert db.query(NguoiDungVaiTro).count() == 0
    assert db.query(LopHocHocVien).count() == 0
    assert db.query(LopHoc).one().GiangVienId is None
    assert db.execute(text("SELECT COUNT(*) FROM PhienDangNhap")).scalar() == 0


def test_delete_user_with_grades_is_blocked_and_preserves_history(db):
    user = add_user(db, 1, "student@example.com")
    class_record = LopHoc(
        MaLop="TEST-01",
        TenLop="Lớp kiểm thử",
        NamHoc="2026-2027",
        NgayTao=datetime.now(),
    )
    subject = MonHoc(
        MaMonHoc="TEST-01",
        TenMonHoc="Môn kiểm thử",
    )
    db.add_all([class_record, subject])
    db.flush()
    grade = Diem(
        LopHocId=class_record.LopHocId,
        HocVienId=user.NguoiDungId,
        MonHocId=subject.MonHocId,
        HocKy=1,
        NamHoc="2026-2027",
        NgayTao=datetime.now(),
        NgayCapNhat=datetime.now(),
    )
    db.add(grade)
    db.commit()

    with pytest.raises(HTTPException) as error:
        delete_user(db, user.NguoiDungId)

    assert error.value.status_code == 409
    assert "dữ liệu điểm" in error.value.detail
    assert db.get(NguoiDung, user.NguoiDungId) is not None
    assert db.query(Diem).count() == 1
