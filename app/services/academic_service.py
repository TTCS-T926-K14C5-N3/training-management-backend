from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.diem import Diem
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.mon_hoc import MonHoc
from app.models.vai_tro import VaiTro


ADMIN_ROLE_ID = 8
TRAINING_MANAGER_ROLE_ID = 7
INSTRUCTOR_ROLE_ID = 3
TEACHING_ASSISTANT_ROLE_ID = 4
TEACHING_ROLE_IDS = frozenset({INSTRUCTOR_ROLE_ID, TEACHING_ASSISTANT_ROLE_ID})
STUDENT_ROLE_ID = 2
ACTIVE_CLASS_STATUSES = ("Đang hoạt động", "Chuẩn bị", "Đang học")


def user_role_ids(db: Session, user_id: int) -> set[int]:
    return {
        role_id
        for (role_id,) in db.query(NguoiDungVaiTro.VaiTroId)
        .filter(NguoiDungVaiTro.NguoiDungId == user_id)
        .all()
    }


def has_schedule_wide_scope(
    db: Session,
    user_id: int,
    role_ids: set[int],
) -> bool:
    if role_ids.intersection({ADMIN_ROLE_ID, TRAINING_MANAGER_ROLE_ID}):
        return True
    role_names = (
        name.lower()
        for (name,) in db.query(VaiTro.TenVaiTro)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.VaiTroId == VaiTro.VaiTroId,
        )
        .filter(NguoiDungVaiTro.NguoiDungId == user_id)
        .all()
    )
    return any(
        "admin" in name or "quản trị" in name
        for name in role_names
    )


def accessible_classes(
    db: Session,
    user: NguoiDung,
    include_inactive: bool = False,
) -> list[LopHoc]:
    roles = user_role_ids(db, user.NguoiDungId)
    query = db.query(LopHoc)

    if not include_inactive:
        query = query.filter(LopHoc.TrangThai.in_(ACTIVE_CLASS_STATUSES))

    if has_schedule_wide_scope(db, user.NguoiDungId, roles):
        return query.order_by(LopHoc.MaLop).all()
    if roles.intersection(TEACHING_ROLE_IDS):
        teaching_classes = db.query(
            LopHocMonHocGiangVien.LopHocId
        ).filter(
            LopHocMonHocGiangVien.GiangVienId == user.NguoiDungId
        )
        if INSTRUCTOR_ROLE_ID in roles:
            return (
                query.filter(
                    or_(
                        LopHoc.GiangVienId == user.NguoiDungId,
                        LopHoc.LopHocId.in_(teaching_classes),
                    )
                )
                .order_by(LopHoc.MaLop)
                .all()
            )
        return (
            query.filter(LopHoc.LopHocId.in_(teaching_classes))
            .order_by(LopHoc.MaLop)
            .all()
        )
    if STUDENT_ROLE_ID in roles:
        return (
            query.join(
                LopHocHocVien,
                LopHocHocVien.LopHocId == LopHoc.LopHocId,
            )
            .filter(LopHocHocVien.HocVienId == user.NguoiDungId)
            .order_by(LopHoc.MaLop)
            .all()
        )
    return []


def can_access_class(
    db: Session,
    user: NguoiDung,
    lop_hoc: LopHoc,
) -> bool:
    roles = user_role_ids(db, user.NguoiDungId)
    if has_schedule_wide_scope(db, user.NguoiDungId, roles):
        return True
    if INSTRUCTOR_ROLE_ID in roles and lop_hoc.GiangVienId == user.NguoiDungId:
        return True
    if roles.intersection(TEACHING_ROLE_IDS):
        return (
            db.query(LopHocMonHocGiangVien)
            .filter(
                LopHocMonHocGiangVien.LopHocId == lop_hoc.LopHocId,
                LopHocMonHocGiangVien.GiangVienId == user.NguoiDungId,
            )
            .first()
            is not None
        )
    if STUDENT_ROLE_ID in roles:
        return (
            db.query(LopHocHocVien)
            .filter(
                LopHocHocVien.LopHocId == lop_hoc.LopHocId,
                LopHocHocVien.HocVienId == user.NguoiDungId,
            )
            .first()
            is not None
        )
    return False


def accessible_grades_query(db: Session, user: NguoiDung):
    roles = user_role_ids(db, user.NguoiDungId)
    query = db.query(Diem)

    if has_schedule_wide_scope(db, user.NguoiDungId, roles):
        return query
    if INSTRUCTOR_ROLE_ID in roles:
        return query.join(LopHoc, LopHoc.LopHocId == Diem.LopHocId).filter(
            LopHoc.GiangVienId == user.NguoiDungId
        )
    if STUDENT_ROLE_ID in roles:
        return query.filter(Diem.HocVienId == user.NguoiDungId)
    return query.filter(Diem.DiemId == -1)


def ensure_valid_academic_year(value: str) -> None:
    parts = value.split("-")
    if (
        len(parts) != 2
        or any(len(part) != 4 or not part.isdigit() for part in parts)
        or int(parts[1]) != int(parts[0]) + 1
    ):
        raise ValueError("Năm học phải có định dạng YYYY-YYYY liên tiếp.")


def ensure_active_student(db: Session, user_id: int) -> NguoiDung:
    student = (
        db.query(NguoiDung)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(
            NguoiDung.NguoiDungId == user_id,
            NguoiDungVaiTro.VaiTroId == STUDENT_ROLE_ID,
            NguoiDung.TrangThai == "HoatDong",
        )
        .first()
    )
    if student is None:
        raise ValueError("Học viên không tồn tại hoặc tài khoản chưa hoạt động.")
    return student


def ensure_active_instructor(db: Session, user_id: int) -> NguoiDung:
    teacher = (
        db.query(NguoiDung)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(
            NguoiDung.NguoiDungId == user_id,
            NguoiDungVaiTro.VaiTroId.in_(TEACHING_ROLE_IDS),
            NguoiDung.TrangThai == "HoatDong",
        )
        .first()
    )
    if teacher is None:
        raise ValueError("Giảng viên không tồn tại hoặc tài khoản chưa hoạt động.")
    return teacher


def ensure_active_subjects(db: Session, subject_ids: list[int]) -> list[MonHoc]:
    requested_ids = set(subject_ids)
    if len(requested_ids) != len(subject_ids):
        raise ValueError("Danh sách môn học không được trùng lặp.")
    if not requested_ids:
        return []

    subjects = (
        db.query(MonHoc)
        .filter(
            MonHoc.MonHocId.in_(requested_ids),
            MonHoc.TrangThai == "Đang hoạt động",
        )
        .all()
    )
    if len(subjects) != len(requested_ids):
        raise ValueError("Có môn học không tồn tại hoặc đã ngừng hoạt động.")
    return subjects
