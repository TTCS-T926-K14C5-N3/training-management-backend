from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.quyen import Quyen
from app.models.vai_tro import VaiTro
from app.models.vai_tro_quyen import VaiTroQuyen
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro


ROLE_NAMES = {
    1: ("Khách", "Người dùng chưa đăng nhập."),
    2: ("Sinh viên", "Người học trong hệ thống."),
    3: ("Giảng viên", "Phụ trách giảng dạy và nhập điểm."),
    4: ("Trợ giảng", "Hỗ trợ hoạt động giảng dạy."),
    5: ("Tuyển sinh", "Quản lý công tác tuyển sinh."),
    6: ("Kế toán", "Quản lý nghiệp vụ học phí."),
    7: ("Quản lý đào tạo", "Điều phối hoạt động đào tạo."),
    8: ("Quản trị hệ thống", "Quản trị người dùng và phân quyền."),
}

PERMISSION_CATALOG = (
    ("USER_VIEW", "Xem người dùng", "Xem danh sách và thông tin người dùng."),
    ("USER_CREATE", "Tạo người dùng", "Tạo hoặc nhập tài khoản người dùng."),
    ("USER_UPDATE", "Sửa người dùng", "Cập nhật thông tin người dùng."),
    ("USER_LOCK", "Khóa người dùng", "Khóa tài khoản người dùng."),
    ("USER_UNLOCK", "Mở khóa người dùng", "Mở khóa tài khoản người dùng."),
    ("USER_DELETE", "Xóa người dùng", "Xóa tài khoản người dùng."),
    (
        "STUDENT_PROFILE_UPDATE",
        "Sửa hồ sơ học viên",
        "Cập nhật thông tin cá nhân và ghi chú hồ sơ học viên.",
    ),
    ("ROLE_VIEW", "Xem vai trò và quyền", "Xem cấu hình vai trò và quyền."),
    ("ROLE_UPDATE", "Cấu hình vai trò và quyền", "Gán quyền cho vai trò và vai trò cho người dùng."),
    ("ROLE_DELETE", "Thu hồi vai trò", "Thu hồi vai trò khỏi người dùng."),
    ("GRADE_VIEW", "Xem điểm", "Xem dữ liệu điểm."),
    ("GRADE_CREATE", "Tạo điểm", "Tạo dữ liệu điểm."),
    ("GRADE_UPDATE", "Sửa điểm", "Thêm hoặc sửa điểm."),
    ("GRADE_DELETE", "Xóa điểm", "Xóa dữ liệu điểm."),
    ("QUAN_LY_DIEM", "Truy cập quản lý điểm", "Truy cập khu vực quản lý điểm."),
    ("TUITION_VIEW", "Xem học phí", "Xem dữ liệu học phí."),
    ("TUITION_CREATE", "Tạo học phí", "Tạo khoản thu học phí."),
    ("TUITION_UPDATE", "Sửa học phí", "Cập nhật học phí hoặc trạng thái thanh toán."),
    ("TUITION_DELETE", "Xóa học phí", "Xóa dữ liệu học phí."),
    ("QUAN_LY_HOC_PHI", "Truy cập quản lý học phí", "Truy cập khu vực quản lý học phí."),
    ("CLASS_VIEW", "Xem lớp học", "Xem dữ liệu lớp học."),
    ("CLASS_CREATE", "Tạo lớp học", "Tạo lớp học."),
    ("CLASS_UPDATE", "Sửa lớp học", "Cập nhật lớp học."),
    ("CLASS_DELETE", "Xóa lớp học", "Xóa lớp học."),
    ("QUAN_LY_LOP", "Truy cập quản lý lớp", "Truy cập khu vực quản lý lớp."),
    ("SCHEDULE_VIEW", "Xem lịch học", "Xem lịch buổi học và lịch sử thay đổi."),
    ("SCHEDULE_CREATE", "Tạo lịch học", "Tạo lịch cho buổi học."),
    ("SCHEDULE_UPDATE", "Cập nhật lịch học", "Chỉnh sửa hoặc hủy buổi học."),
    ("ATTENDANCE_VIEW", "Xem điểm danh", "Xem danh sách và kết quả điểm danh theo buổi."),
    ("ATTENDANCE_UPDATE", "Ghi nhận điểm danh", "Ghi nhận hoặc cập nhật điểm danh theo buổi."),
    ("ASSIGNMENT_VIEW", "Xem bài tập", "Xem bài tập và trạng thái nộp bài."),
    ("ASSIGNMENT_CREATE", "Quản lý bài tập", "Tạo và giao bài tập cho lớp."),
    ("ASSIGNMENT_SUBMIT", "Nộp bài tập", "Nộp và cập nhật bài làm."),
    ("ASSIGNMENT_GRADE", "Chấm bài tập", "Xem danh sách bài nộp và chấm bài."),
    ("CURRICULUM_VIEW", "Xem danh mục đào tạo", "Xem môn học và cấu trúc chương trình."),
    ("CURRICULUM_CREATE", "Tạo danh mục đào tạo", "Tạo môn học trong danh mục đào tạo."),
    ("CURRICULUM_UPDATE", "Sửa danh mục đào tạo", "Sửa môn học và cấu trúc chương trình."),
    ("CURRICULUM_DELETE", "Lưu trữ danh mục đào tạo", "Lưu trữ môn học trong danh mục đào tạo."),
    ("LEAD_VIEW", "Xem khách hàng tiềm năng", "Xem hồ sơ tuyển sinh được phép truy cập."),
    ("LEAD_CREATE", "Tạo khách hàng tiềm năng", "Tạo hồ sơ khách hàng tiềm năng."),
    ("LEAD_UPDATE", "Sửa khách hàng tiềm năng", "Cập nhật hồ sơ khách hàng tiềm năng."),
    ("LEAD_DELETE", "Xóa khách hàng tiềm năng", "Xóa hồ sơ khách hàng tiềm năng."),
    ("LEAD_ASSIGN", "Phân công tư vấn", "Phân công khách hàng tiềm năng cho tư vấn viên."),
)

DEFAULT_ROLE_PERMISSIONS = {
    1: (),
    2: ("GRADE_VIEW", "TUITION_VIEW", "ASSIGNMENT_VIEW", "ASSIGNMENT_SUBMIT"),
    3: (
        "GRADE_VIEW",
        "GRADE_CREATE",
        "GRADE_UPDATE",
        "QUAN_LY_DIEM",
        "CLASS_VIEW",
        "SCHEDULE_VIEW",
        "ATTENDANCE_VIEW",
        "ATTENDANCE_UPDATE",
        "CURRICULUM_VIEW",
        "ASSIGNMENT_VIEW",
        "ASSIGNMENT_CREATE",
        "ASSIGNMENT_GRADE",
    ),
    4: (
        "SCHEDULE_VIEW",
        "ATTENDANCE_VIEW",
        "ATTENDANCE_UPDATE",
        "ASSIGNMENT_VIEW",
        "ASSIGNMENT_CREATE",
        "ASSIGNMENT_GRADE",
    ),
    5: (
        "USER_VIEW",
        "USER_CREATE",
        "USER_UPDATE",
        "LEAD_VIEW",
        "LEAD_CREATE",
        "LEAD_UPDATE",
    ),
    6: ("TUITION_VIEW", "TUITION_CREATE", "TUITION_UPDATE", "QUAN_LY_HOC_PHI"),
    7: (
        "USER_VIEW",
        "STUDENT_PROFILE_UPDATE",
        "ROLE_VIEW",
        "GRADE_VIEW",
        "TUITION_VIEW",
        "CLASS_VIEW",
        "CLASS_CREATE",
        "CLASS_UPDATE",
        "CLASS_DELETE",
        "QUAN_LY_LOP",
        "SCHEDULE_VIEW",
        "SCHEDULE_CREATE",
        "SCHEDULE_UPDATE",
        "ATTENDANCE_VIEW",
        "ATTENDANCE_UPDATE",
        "CURRICULUM_VIEW",
        "CURRICULUM_CREATE",
        "CURRICULUM_UPDATE",
        "CURRICULUM_DELETE",
        "LEAD_VIEW",
        "LEAD_CREATE",
        "LEAD_UPDATE",
        "LEAD_DELETE",
        "LEAD_ASSIGN",
        "ASSIGNMENT_VIEW",
        "ASSIGNMENT_CREATE",
        "ASSIGNMENT_GRADE",
    ),
    8: tuple(code for code, _name, _description in PERMISSION_CATALOG),
}


def initialize_role_permissions(db: Session) -> None:
    """Create the eight system roles and permission catalog if they are absent."""
    existing_roles = {
        role_id
        for (role_id,) in db.query(VaiTro.VaiTroId)
        .filter(VaiTro.VaiTroId.between(1, 8))
        .all()
    }
    missing_roles = [
        (role_id, name, description)
        for role_id, (name, description) in ROLE_NAMES.items()
        if role_id not in existing_roles
    ]

    if missing_roles:
        db.execute(text("SET IDENTITY_INSERT dbo.VaiTro ON"))
        try:
            for role_id, name, description in missing_roles:
                db.execute(
                    text("""
                    INSERT INTO dbo.VaiTro (VaiTroId, TenVaiTro, MoTa)
                    VALUES (:role_id, :name, :description)
                    """),
                    {
                        "role_id": role_id,
                        "name": name,
                        "description": description,
                    },
                )
        finally:
            db.execute(text("SET IDENTITY_INSERT dbo.VaiTro OFF"))

    permissions_by_code = {
        permission.MaQuyen: permission
        for permission in db.query(Quyen).all()
    }
    new_permission_codes = set()
    for code, name, description in PERMISSION_CATALOG:
        if code not in permissions_by_code:
            permission = Quyen(
                MaQuyen=code,
                TenQuyen=name,
                MoTa=description,
            )
            db.add(permission)
            permissions_by_code[code] = permission
            new_permission_codes.add(code)

    db.flush()

    role_permission_count = db.query(VaiTroQuyen).count()
    if role_permission_count == 0:
        for role_id, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
            for code in permission_codes:
                db.add(
                    VaiTroQuyen(
                        VaiTroId=role_id,
                        QuyenId=permissions_by_code[code].QuyenId,
                    )
                )
    else:
        for role_id, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
            for code in permission_codes:
                if code in new_permission_codes:
                    db.add(
                        VaiTroQuyen(
                            VaiTroId=role_id,
                            QuyenId=permissions_by_code[code].QuyenId,
                        )
                    )

        db.flush()
        admin_role_permissions = {
            link.QuyenId
            for link in db.query(VaiTroQuyen)
            .filter(VaiTroQuyen.VaiTroId == 8)
            .all()
        }
        for code in ("ROLE_VIEW", "ROLE_UPDATE"):
            permission_id = permissions_by_code[code].QuyenId
            if permission_id not in admin_role_permissions:
                db.add(
                    VaiTroQuyen(
                        VaiTroId=8,
                        QuyenId=permission_id,
                    )
                )

    db.commit()


def list_permission_catalog() -> list[dict[str, str]]:
    return [
        {
            "maQuyen": code,
            "tenQuyen": name,
            "moTa": description,
        }
        for code, name, description in PERMISSION_CATALOG
    ]


def replace_role_permissions(
    db: Session,
    role_id: int,
    permission_codes: list[str],
) -> list[dict[str, str | int]]:
    role = (
        db.query(VaiTro)
        .filter(VaiTro.VaiTroId == role_id, VaiTro.VaiTroId <= 8)
        .first()
    )
    if role is None:
        raise ValueError("Vai trò không tồn tại.")

    available_codes = {code for code, _name, _description in PERMISSION_CATALOG}
    requested_codes = set(permission_codes)
    unknown_codes = requested_codes - available_codes
    if unknown_codes:
        raise ValueError(
            f"Mã quyền không hợp lệ: {', '.join(sorted(unknown_codes))}."
        )

    if role_id == 8 and not {"ROLE_VIEW", "ROLE_UPDATE"} <= requested_codes:
        raise ValueError(
            "Quản trị hệ thống phải giữ quyền xem và cấu hình vai trò."
        )

    permissions = {
        permission.MaQuyen: permission
        for permission in db.query(Quyen)
        .filter(Quyen.MaQuyen.in_(requested_codes))
        .all()
    }
    missing_codes = requested_codes - set(permissions)
    if missing_codes:
        raise ValueError(
            f"Quyền chưa được khởi tạo: {', '.join(sorted(missing_codes))}."
        )

    current_links = (
        db.query(VaiTroQuyen)
        .filter(VaiTroQuyen.VaiTroId == role_id)
        .all()
    )

    try:
        for link in current_links:
            db.delete(link)

        for code in sorted(requested_codes):
            db.add(
                VaiTroQuyen(
                    VaiTroId=role_id,
                    QuyenId=permissions[code].QuyenId,
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        raise

    return [
        {
            "quyenId": permissions[code].QuyenId,
            "maQuyen": code,
            "tenQuyen": permissions[code].TenQuyen,
        }
        for code in sorted(requested_codes)
    ]


def list_user_permissions(db: Session, user_id: int) -> list[dict[str, str | int]]:
    permissions = (
        db.query(Quyen)
        .join(
            VaiTroQuyen,
            VaiTroQuyen.QuyenId == Quyen.QuyenId,
        )
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.VaiTroId == VaiTroQuyen.VaiTroId,
        )
        .filter(NguoiDungVaiTro.NguoiDungId == user_id)
        .order_by(Quyen.QuyenId)
        .all()
    )
    unique_permissions = {permission.MaQuyen: permission for permission in permissions}
    return [
        {
            "quyenId": permission.QuyenId,
            "maQuyen": permission.MaQuyen,
            "tenQuyen": permission.TenQuyen,
        }
        for permission in unique_permissions.values()
    ]
