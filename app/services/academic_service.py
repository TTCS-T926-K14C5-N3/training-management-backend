from sqlalchemy import false
from sqlalchemy.orm import Session

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
ASSISTANT_ROLE_ID = 4
TEACHING_ROLE_IDS = {INSTRUCTOR_ROLE_ID, ASSISTANT_ROLE_ID}
STUDENT_ROLE_ID = 2
ADMIN_ROLE_NAMES = {
    "admin",
    "quản trị hệ thống",
    "quản trị viên hệ thống",
}

# Exact status strings persisted by the user writers (auth_service,
# user_import_service) and guarded by the CK_NguoiDung_TrangThai constraint.
ACTIVE_USER_STATUS = "HoatDong"
LOCKED_USER_STATUS = "BiKhoa"
ACTIVE_CLASS_STATUSES = {"Chuẩn bị", "Đang học", "Đang hoạt động"}


def user_role_ids(db: Session, user_id: int) -> set[int]:
    return {
        role_id
        for (role_id,) in db.query(NguoiDungVaiTro.VaiTroId)
        .filter(NguoiDungVaiTro.NguoiDungId == user_id)
        .all()
    }


def user_is_admin(db: Session, user_id: int) -> bool:
    roles = (
        db.query(VaiTro.VaiTroId, VaiTro.TenVaiTro)
        .join(NguoiDungVaiTro, NguoiDungVaiTro.VaiTroId == VaiTro.VaiTroId)
        .filter(NguoiDungVaiTro.NguoiDungId == user_id)
        .all()
    )
    return any(
        role_id == ADMIN_ROLE_ID
        or role_name.strip().casefold() in ADMIN_ROLE_NAMES
        for role_id, role_name in roles
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

    if user_is_admin(db, user.NguoiDungId) or TRAINING_MANAGER_ROLE_ID in roles:
        return query.order_by(LopHoc.MaLop).all()
    if roles.intersection(TEACHING_ROLE_IDS):
        assigned_subject_class_ids = (
            db.query(LopHocMonHocGiangVien.LopHocId)
            .filter(LopHocMonHocGiangVien.GiangVienId == user.NguoiDungId)
        )
        return (
            query.filter(
                (LopHoc.GiangVienId == user.NguoiDungId)
                | LopHoc.LopHocId.in_(assigned_subject_class_ids)
            )
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
    if user_is_admin(db, user.NguoiDungId) or TRAINING_MANAGER_ROLE_ID in roles:
        return True
    if roles.intersection(TEACHING_ROLE_IDS):
        return lop_hoc.GiangVienId == user.NguoiDungId or (
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

    if user_is_admin(db, user.NguoiDungId) or TRAINING_MANAGER_ROLE_ID in roles:
        return query
    if roles.intersection(TEACHING_ROLE_IDS):
        assigned_class_ids = db.query(LopHoc.LopHocId).filter(
            LopHoc.GiangVienId == user.NguoiDungId
        ).union(
            db.query(LopHocMonHocGiangVien.LopHocId).filter(
                LopHocMonHocGiangVien.GiangVienId == user.NguoiDungId
            )
        )
        return query.filter(Diem.LopHocId.in_(assigned_class_ids))
    if STUDENT_ROLE_ID in roles:
        return query.filter(Diem.HocVienId == user.NguoiDungId)
    return query.filter(false())


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
            NguoiDung.TrangThai == ACTIVE_USER_STATUS,
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
            NguoiDung.TrangThai == ACTIVE_USER_STATUS,
        )
        .first()
    )
    if teacher is None:
        raise ValueError("Giảng viên không tồn tại hoặc tài khoản chưa hoạt động.")
    return teacher


def ensure_active_teaching_role(
    db: Session,
    user_id: int,
    required_role_id: int,
) -> NguoiDung:
    teacher = (
        db.query(NguoiDung)
        .filter(
            NguoiDung.NguoiDungId == user_id,
            NguoiDung.TrangThai == ACTIVE_USER_STATUS,
        )
        .first()
    )
    if teacher is None or required_role_id not in user_role_ids(db, user_id):
        role_name = "giảng viên chính" if required_role_id == INSTRUCTOR_ROLE_ID else "trợ giảng"
        raise ValueError(f"Tài khoản không có vai trò {role_name} hoặc chưa hoạt động.")
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


def build_prerequisite_map(
    items: list[tuple[int, int | None]],
) -> dict[int, int]:
    """Kiểm tra quan hệ môn tiên quyết của một chương trình.

    `items` là danh sách (mon_hoc_id, mon_tien_quyet_id) của chương trình.
    Trả về map mon_hoc_id -> mon_tien_quyet_id cho các môn có tiên quyết.

    Raise ValueError khi:
    - môn học là tiên quyết của chính nó
    - môn tiên quyết không thuộc cùng chương trình
    - quan hệ tiên quyết tạo vòng lặp
    """

    requested_subject_ids = {mon_hoc_id for mon_hoc_id, _ in items}

    for mon_hoc_id, mon_tien_quyet_id in items:
        if mon_tien_quyet_id is None:
            continue
        if mon_tien_quyet_id == mon_hoc_id:
            raise ValueError("Môn học không thể là tiên quyết của chính nó.")
        if mon_tien_quyet_id not in requested_subject_ids:
            raise ValueError("Môn tiên quyết phải thuộc cùng chương trình.")

    prerequisite_by_subject = {
        mon_hoc_id: mon_tien_quyet_id
        for mon_hoc_id, mon_tien_quyet_id in items
        if mon_tien_quyet_id is not None
    }

    for subject_id in requested_subject_ids:
        seen = set()
        cursor = subject_id
        while cursor in prerequisite_by_subject:
            cursor = prerequisite_by_subject[cursor]
            if cursor in seen or cursor == subject_id:
                raise ValueError("Quan hệ môn tiên quyết không được tạo vòng lặp.")
            seen.add(cursor)

    return prerequisite_by_subject
