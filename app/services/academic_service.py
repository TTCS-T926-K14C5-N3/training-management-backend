from sqlalchemy import false
from sqlalchemy.orm import Session

from app.models.diem import Diem
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.mon_hoc import MonHoc


ADMIN_ROLE_ID = 8
TRAINING_MANAGER_ROLE_ID = 7
INSTRUCTOR_ROLE_ID = 3
STUDENT_ROLE_ID = 2

# Exact status strings persisted by the user writers (auth_service,
# user_import_service) and guarded by the CK_NguoiDung_TrangThai constraint.
ACTIVE_USER_STATUS = "HoatDong"
LOCKED_USER_STATUS = "BiKhoa"


def user_role_ids(db: Session, user_id: int) -> set[int]:
    return {
        role_id
        for (role_id,) in db.query(NguoiDungVaiTro.VaiTroId)
        .filter(NguoiDungVaiTro.NguoiDungId == user_id)
        .all()
    }


def accessible_classes(
    db: Session,
    user: NguoiDung,
    include_inactive: bool = False,
) -> list[LopHoc]:
    roles = user_role_ids(db, user.NguoiDungId)
    query = db.query(LopHoc)

    if not include_inactive:
        query = query.filter(LopHoc.TrangThai == "Đang hoạt động")

    if roles.intersection({ADMIN_ROLE_ID, TRAINING_MANAGER_ROLE_ID}):
        return query.order_by(LopHoc.MaLop).all()
    if INSTRUCTOR_ROLE_ID in roles:
        return (
            query.filter(LopHoc.GiangVienId == user.NguoiDungId)
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
    if roles.intersection({ADMIN_ROLE_ID, TRAINING_MANAGER_ROLE_ID}):
        return True
    if INSTRUCTOR_ROLE_ID in roles:
        return lop_hoc.GiangVienId == user.NguoiDungId
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

    if roles.intersection({ADMIN_ROLE_ID, TRAINING_MANAGER_ROLE_ID}):
        return query
    if INSTRUCTOR_ROLE_ID in roles:
        return query.join(LopHoc, LopHoc.LopHocId == Diem.LopHocId).filter(
            LopHoc.GiangVienId == user.NguoiDungId
        )
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
            NguoiDungVaiTro.VaiTroId == INSTRUCTOR_ROLE_ID,
            NguoiDung.TrangThai == ACTIVE_USER_STATUS,
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
