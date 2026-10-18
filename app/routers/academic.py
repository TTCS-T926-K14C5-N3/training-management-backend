from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.diem import Diem
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.curriculum import (
    ProgramSession,
    ProgramSubject,
    ProgramSubjectPrerequisite,
)
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.mon_hoc import MonHoc
from app.models.phong_hoc import PhongHoc
from app.models.quyen import Quyen
from app.models.student_enrollment_action import StudentEnrollmentAction
from app.models.tuyen_sinh_lead_chuyen_doi import TuyenSinhLeadChuyenDoi
from app.models.vai_tro_quyen import VaiTroQuyen
from app.schemas.academic import (
    ClassEnrollmentsWrite,
    ClassWrite,
    GradeWrite,
    RoomCreate,
    StudentEnrollmentActionWrite,
    StudentProfileUpdate,
    SubjectCreate,
    SubjectUpdate,
    TrainingProgramWrite,
)
from app.schemas.curriculum import (
    ProgramSessionsClone,
    ProgramSessionsWrite,
    ProgramSubjectsWrite,
)
from app.services.academic_service import (
    ACTIVE_CLASS_STATUSES,
    INSTRUCTOR_ROLE_ID,
    STUDENT_ROLE_ID,
    TEACHING_ASSISTANT_ROLE_ID,
    TEACHING_ROLE_IDS,
    accessible_classes,
    accessible_grades_query,
    can_access_class,
    ensure_active_instructor,
    ensure_active_student,
    ensure_active_subjects,
    ensure_valid_academic_year,
    has_schedule_wide_scope,
    user_role_ids,
)
from app.services.business_time import business_now, business_now_naive


router = APIRouter(prefix="/academic", tags=["Academic management"])


def _commit(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=message,
        ) from error


def _get_class_or_404(db: Session, class_id: int) -> LopHoc:
    lop_hoc = (
        db.query(LopHoc)
        .filter(LopHoc.LopHocId == class_id)
        .first()
    )
    if lop_hoc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy lớp học.",
        )
    return lop_hoc


def _ensure_class_scope(db: Session, user: NguoiDung, lop_hoc: LopHoc) -> None:
    if not can_access_class(db, user, lop_hoc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công hoặc ghi danh trong lớp học này.",
        )


def _has_permission(db: Session, user_id: int, permission_code: str) -> bool:
    return (
        db.query(Quyen.QuyenId)
        .join(VaiTroQuyen, VaiTroQuyen.QuyenId == Quyen.QuyenId)
        .join(NguoiDungVaiTro, NguoiDungVaiTro.VaiTroId == VaiTroQuyen.VaiTroId)
        .filter(
            NguoiDungVaiTro.NguoiDungId == user_id,
            Quyen.MaQuyen == permission_code,
        )
        .first()
        is not None
    )


def _ensure_permission_or_admin(
    db: Session,
    user: NguoiDung,
    permission_code: str,
) -> None:
    roles = user_role_ids(db, user.NguoiDungId)
    if _has_permission(db, user.NguoiDungId, permission_code) or has_schedule_wide_scope(
        db,
        user.NguoiDungId,
        roles,
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Bạn không có quyền thực hiện chức năng này.",
    )


def _class_payload(db: Session, lop_hoc: LopHoc) -> dict:
    program = (
        db.query(ChuongTrinhDaoTao)
        .filter(ChuongTrinhDaoTao.ChuongTrinhId == lop_hoc.ChuongTrinhId)
        .first()
        if lop_hoc.ChuongTrinhId is not None
        else None
    )
    teacher = (
        db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId == lop_hoc.GiangVienId)
        .first()
        if lop_hoc.GiangVienId is not None
        else None
    )
    students = (
        db.query(NguoiDung)
        .join(
            LopHocHocVien,
            LopHocHocVien.HocVienId == NguoiDung.NguoiDungId,
        )
        .filter(LopHocHocVien.LopHocId == lop_hoc.LopHocId)
        .order_by(NguoiDung.HoTen)
        .all()
    )
    subjects = (
        db.query(MonHoc)
        .join(
            LopHocMonHoc,
            LopHocMonHoc.MonHocId == MonHoc.MonHocId,
        )
        .filter(LopHocMonHoc.LopHocId == lop_hoc.LopHocId)
        .order_by(MonHoc.MaMonHoc)
        .all()
    )
    room = (
        db.query(PhongHoc)
        .filter(PhongHoc.PhongHocId == lop_hoc.PhongHocId)
        .first()
        if lop_hoc.PhongHocId is not None
        else None
    )
    assignments = (
        db.query(LopHocMonHocGiangVien)
        .filter(LopHocMonHocGiangVien.LopHocId == lop_hoc.LopHocId)
        .order_by(
            LopHocMonHocGiangVien.MonHocId,
            LopHocMonHocGiangVien.VaiTro,
            LopHocMonHocGiangVien.GiangVienId,
        )
        .all()
    )
    return {
        "lopHocId": lop_hoc.LopHocId,
        "maLop": lop_hoc.MaLop,
        "tenLop": lop_hoc.TenLop,
        "namHoc": lop_hoc.NamHoc,
        "chuongTrinhId": lop_hoc.ChuongTrinhId,
        "maChuongTrinh": program.MaChuongTrinh if program else None,
        "tenChuongTrinh": program.TenChuongTrinh if program else None,
        "giangVienId": lop_hoc.GiangVienId,
        "giangVienTen": teacher.HoTen if teacher else None,
        "canBanGiao": teacher is not None and teacher.TrangThai == "BiKhoa",
        "trangThai": lop_hoc.TrangThai,
        "ngayKhaiGiang": lop_hoc.NgayKhaiGiang.isoformat(),
        "siSoHienTai": len(students),
        "siSoToiDa": lop_hoc.SiSoToiDa,
        "canhBaoSiSo": len(students) >= lop_hoc.SiSoToiDa,
        "hinhThuc": lop_hoc.HinhThuc,
        "phongHocId": lop_hoc.PhongHocId,
        "maPhong": room.MaPhong if room else None,
        "tenPhong": room.TenPhong if room else None,
        "sucChuaPhong": room.SucChua if room else None,
        "canhBaoSucChuaPhong": (
            room is not None and len(students) > room.SucChua
        ),
        "linkTrucTuyen": lop_hoc.LinkTrucTuyen,
        "tienDo": float(lop_hoc.TienDo),
        "phanCongGiangVien": [
            {
                "monHocId": assignment.MonHocId,
                "giangVienId": assignment.GiangVienId,
                "vaiTro": assignment.VaiTro,
            }
            for assignment in assignments
        ],
        "hocVienIds": [student.NguoiDungId for student in students],
        "hocViens": [
            {
                "nguoiDungId": student.NguoiDungId,
                "hoTen": student.HoTen,
                "email": student.Email,
            }
            for student in students
        ],
        "monHocIds": [subject.MonHocId for subject in subjects],
        "monHocs": [
            {
                "monHocId": subject.MonHocId,
                "maMonHoc": subject.MaMonHoc,
                "tenMonHoc": subject.TenMonHoc,
            }
            for subject in subjects
        ],
    }


def _room_payload(room: PhongHoc) -> dict:
    return {
        "phongHocId": room.PhongHocId,
        "maPhong": room.MaPhong,
        "tenPhong": room.TenPhong,
        "sucChua": room.SucChua,
    }


def _grade_payload(db: Session, grade: Diem) -> dict:
    student = db.query(NguoiDung).filter(
        NguoiDung.NguoiDungId == grade.HocVienId
    ).first()
    lop_hoc = db.query(LopHoc).filter(
        LopHoc.LopHocId == grade.LopHocId
    ).first()
    subject = db.query(MonHoc).filter(
        MonHoc.MonHocId == grade.MonHocId
    ).first()
    return {
        "diemId": grade.DiemId,
        "lopHocId": grade.LopHocId,
        "maLop": lop_hoc.MaLop if lop_hoc else "",
        "tenLop": lop_hoc.TenLop if lop_hoc else "",
        "hocVienId": grade.HocVienId,
        "hocVienTen": student.HoTen if student else "",
        "monHocId": grade.MonHocId,
        "maMonHoc": subject.MaMonHoc if subject else "",
        "tenMonHoc": subject.TenMonHoc if subject else "",
        "hocKy": grade.HocKy,
        "namHoc": grade.NamHoc,
        "diemQuaTrinh": (
            float(grade.DiemQuaTrinh)
            if grade.DiemQuaTrinh is not None
            else None
        ),
        "diemGiuaKy": (
            float(grade.DiemGiuaKy)
            if grade.DiemGiuaKy is not None
            else None
        ),
        "diemCuoiKy": (
            float(grade.DiemCuoiKy)
            if grade.DiemCuoiKy is not None
            else None
        ),
    }


def _apply_class_write(
    db: Session,
    lop_hoc: LopHoc,
    request: ClassWrite,
) -> None:
    if not request.ma_lop.strip() or not request.ten_lop.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mã lớp và tên lớp không được để trống.",
        )
    ensure_valid_academic_year(request.nam_hoc)
    program = None
    if request.chuong_trinh_id is not None:
        program = (
            db.query(ChuongTrinhDaoTao)
            .filter(
                ChuongTrinhDaoTao.ChuongTrinhId == request.chuong_trinh_id
            )
            .first()
        )
        if program is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Chương trình đào tạo không tồn tại.",
            )
        if (
            program.TrangThai != "Đang áp dụng"
            and request.chuong_trinh_id != lop_hoc.ChuongTrinhId
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Chỉ được mở lớp bằng chương trình đang áp dụng.",
            )
    student_ids = set(request.hoc_vien_ids)
    if len(student_ids) != len(request.hoc_vien_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Danh sách học viên không được trùng lặp.",
        )

    try:
        if request.giang_vien_id is not None:
            ensure_active_instructor(db, request.giang_vien_id)
        if request.phong_hoc_id is not None and db.query(PhongHoc).filter(
            PhongHoc.PhongHocId == request.phong_hoc_id
        ).first() is None:
            raise ValueError("Phòng học không tồn tại.")
        if request.phan_cong_giang_vien is not None:
            assignment_keys = [
                (item.mon_hoc_id, item.giang_vien_id)
                for item in request.phan_cong_giang_vien
            ]
            if len(assignment_keys) != len(set(assignment_keys)):
                raise ValueError("Phân công giảng viên không được trùng lặp.")
            for assignment in request.phan_cong_giang_vien:
                if assignment.mon_hoc_id not in request.mon_hoc_ids:
                    raise ValueError(
                        "Chỉ được phân công giảng viên cho môn học của lớp."
                    )
                ensure_active_instructor(db, assignment.giang_vien_id)
                roles = user_role_ids(db, assignment.giang_vien_id)
                required_role = (
                    INSTRUCTOR_ROLE_ID
                    if assignment.vai_tro == "Chính"
                    else TEACHING_ASSISTANT_ROLE_ID
                )
                if required_role not in roles:
                    raise ValueError(
                        "Vai trò giảng viên không khớp với loại phân công."
                    )
        for student_id in sorted(student_ids):
            ensure_active_student(db, student_id)
        ensure_active_subjects(db, request.mon_hoc_ids)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    current_students = {
        link.HocVienId
        for link in db.query(LopHocHocVien)
        .filter(LopHocHocVien.LopHocId == lop_hoc.LopHocId)
        .all()
    }
    removed_students = current_students - student_ids
    if removed_students:
        has_grades = (
            db.query(Diem.DiemId)
            .filter(
                Diem.LopHocId == lop_hoc.LopHocId,
                Diem.HocVienId.in_(removed_students),
            )
            .first()
            is not None
        )
        if has_grades:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Không thể gỡ học viên đã có điểm khỏi lớp.",
            )

    current_subjects = {
        link.MonHocId
        for link in db.query(LopHocMonHoc)
        .filter(LopHocMonHoc.LopHocId == lop_hoc.LopHocId)
        .all()
    }
    removed_subjects = current_subjects - set(request.mon_hoc_ids)
    if removed_subjects:
        has_grades = (
            db.query(Diem.DiemId)
            .filter(
                Diem.LopHocId == lop_hoc.LopHocId,
                Diem.MonHocId.in_(removed_subjects),
            )
            .first()
            is not None
        )
        if has_grades:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Không thể gỡ môn học đã có điểm khỏi lớp.",
            )

    assignment_query = db.query(LopHocMonHocGiangVien).filter(
        LopHocMonHocGiangVien.LopHocId == lop_hoc.LopHocId
    )
    if request.phan_cong_giang_vien is not None:
        assignment_query.delete(synchronize_session=False)
    elif removed_subjects:
        assignment_query.filter(
            LopHocMonHocGiangVien.MonHocId.in_(removed_subjects)
        ).delete(synchronize_session=False)

    lop_hoc.MaLop = request.ma_lop.strip()
    lop_hoc.TenLop = request.ten_lop.strip()
    lop_hoc.NamHoc = request.nam_hoc
    lop_hoc.ChuongTrinhId = request.chuong_trinh_id
    lop_hoc.GiangVienId = request.giang_vien_id
    lop_hoc.NgayKhaiGiang = request.ngay_khai_giang
    lop_hoc.SiSoToiDa = request.si_so_toi_da
    lop_hoc.HinhThuc = request.hinh_thuc
    lop_hoc.PhongHocId = request.phong_hoc_id
    lop_hoc.LinkTrucTuyen = request.link_truc_tuyen
    lop_hoc.TienDo = request.tien_do

    for student_id in current_students - student_ids:
        db.query(LopHocHocVien).filter(
            LopHocHocVien.LopHocId == lop_hoc.LopHocId,
            LopHocHocVien.HocVienId == student_id,
        ).delete(synchronize_session=False)
    for student_id in student_ids - current_students:
        db.add(
            LopHocHocVien(
                LopHocId=lop_hoc.LopHocId,
                HocVienId=student_id,
                NgayThamGia=datetime.now(),
            )
        )

    for subject_id in removed_subjects:
        db.query(LopHocMonHoc).filter(
            LopHocMonHoc.LopHocId == lop_hoc.LopHocId,
            LopHocMonHoc.MonHocId == subject_id,
        ).delete(synchronize_session=False)
    for subject_id in set(request.mon_hoc_ids) - current_subjects:
        db.add(
            LopHocMonHoc(
                LopHocId=lop_hoc.LopHocId,
                MonHocId=subject_id,
            )
        )
    if request.phan_cong_giang_vien is not None:
        db.add_all(
            LopHocMonHocGiangVien(
                LopHocId=lop_hoc.LopHocId,
                MonHocId=assignment.mon_hoc_id,
                GiangVienId=assignment.giang_vien_id,
                VaiTro=assignment.vai_tro,
            )
            for assignment in request.phan_cong_giang_vien
        )


def _validate_grade_scope(
    db: Session,
    user: NguoiDung,
    request: GradeWrite,
) -> LopHoc:
    try:
        ensure_valid_academic_year(request.nam_hoc)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    lop_hoc = _get_class_or_404(db, request.lop_hoc_id)
    if lop_hoc.TrangThai not in ACTIVE_CLASS_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể nhập điểm cho lớp đã ngừng hoạt động.",
        )
    _ensure_class_scope(db, user, lop_hoc)

    enrolled = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == lop_hoc.LopHocId,
            LopHocHocVien.HocVienId == request.hoc_vien_id,
        )
        .first()
        is not None
    )
    if not enrolled:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Học viên chưa được ghi danh trong lớp này.",
        )

    subject_assigned = (
        db.query(LopHocMonHoc)
        .filter(
            LopHocMonHoc.LopHocId == lop_hoc.LopHocId,
            LopHocMonHoc.MonHocId == request.mon_hoc_id,
        )
        .first()
        is not None
    )
    if not subject_assigned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Môn học chưa được gán cho lớp này.",
        )
    return lop_hoc


def _student_is_visible(
    db: Session,
    current_user: NguoiDung,
    student_id: int,
) -> bool:
    roles = user_role_ids(db, current_user.NguoiDungId)
    if has_schedule_wide_scope(db, current_user.NguoiDungId, roles):
        return True
    if student_id == current_user.NguoiDungId and STUDENT_ROLE_ID in roles:
        return True
    visible_class_ids = [
        lop_hoc.LopHocId
        for lop_hoc in accessible_classes(
            db,
            current_user,
            include_inactive=True,
        )
    ]
    return bool(
        visible_class_ids
        and db.query(LopHocHocVien.LopHocId)
        .filter(
            LopHocHocVien.HocVienId == student_id,
            LopHocHocVien.LopHocId.in_(visible_class_ids),
        )
        .first()
    )


def _student_enrollment_status(
    class_record: LopHoc,
    actions: list[StudentEnrollmentAction],
    as_of: date,
) -> tuple[str, date | None]:
    relevant_actions = [
        action for action in actions if action.LopHocId == class_record.LopHocId
    ]
    incoming_transfers = [
        action
        for action in actions
        if action.LoaiThaoTac == "ChuyenLop"
        and action.LopHocDichId == class_record.LopHocId
    ]
    future_incoming = [
        action for action in incoming_transfers if action.NgayHieuLuc > as_of
    ]
    if future_incoming:
        action = min(future_incoming, key=lambda item: item.NgayHieuLuc)
        return "Sắp chuyển lớp", action.NgayHieuLuc

    effective_actions = [
        action for action in relevant_actions if action.NgayHieuLuc <= as_of
    ]
    if effective_actions:
        action = max(
            effective_actions,
            key=lambda item: (item.NgayHieuLuc, item.ActionId),
        )
        status_by_action = {
            "BaoLuu": "Bảo lưu",
            "ChuyenLop": "Đã chuyển lớp",
            "ThoiHoc": "Thôi học",
        }
        return status_by_action[action.LoaiThaoTac], action.NgayHieuLuc

    future_actions = [
        action for action in relevant_actions if action.NgayHieuLuc > as_of
    ]
    if future_actions:
        action = min(future_actions, key=lambda item: item.NgayHieuLuc)
        status_by_action = {
            "BaoLuu": "Sắp bảo lưu",
            "ChuyenLop": "Sắp chuyển lớp",
            "ThoiHoc": "Sắp thôi học",
        }
        return status_by_action[action.LoaiThaoTac], action.NgayHieuLuc

    if class_record.TrangThai in {"Chuẩn bị", "Đang hoạt động", "Đang học"}:
        return "Đang học", None
    return "Đã kết thúc", None


def _student_status_payload_from_records(
    student: NguoiDung,
    conversion: TuyenSinhLeadChuyenDoi | None,
    enrollments: list[tuple[LopHocHocVien, LopHoc]],
    actions: list[StudentEnrollmentAction],
    role_ids: set[int],
    class_filter: int | None = None,
    visible_class_ids: set[int] | None = None,
) -> dict:
    as_of = business_now().date()
    class_rows = [
        (enrollment, lop_hoc)
        for enrollment, lop_hoc in enrollments
        if class_filter is None or lop_hoc.LopHocId == class_filter
        if visible_class_ids is None or lop_hoc.LopHocId in visible_class_ids
    ]
    class_statuses = [
        (
            enrollment,
            lop_hoc,
            *_student_enrollment_status(lop_hoc, actions, as_of),
        )
        for enrollment, lop_hoc in class_rows
    ]
    if not enrollments or not class_statuses:
        enrollment_status = "Chưa ghi danh"
        effective_date = None
    else:
        preferred = next(
            (row for row in class_statuses if row[2] == "Đang học"),
            class_statuses[0],
        )
        enrollment_status = preferred[2]
        effective_date = preferred[3]

    return {
        "nguoiDungId": student.NguoiDungId,
        "maHocVien": conversion.MaHocVien if conversion else None,
        "hoTen": student.HoTen,
        "email": student.Email,
        "soDienThoai": student.SoDienThoai,
        "trangThai": student.TrangThai,
        "trangThaiTaiKhoan": student.TrangThai,
        "vaiTroId": min(role_ids) if role_ids else None,
        "vaiTroIds": sorted(role_ids),
        "vaiTro": "Học viên",
        "trangThaiGhiDanh": enrollment_status,
        "ngayHieuLuc": effective_date.isoformat() if effective_date else None,
        "lopHienTai": [
            {
                "lopHocId": lop_hoc.LopHocId,
                "maLop": lop_hoc.MaLop,
                "tenLop": lop_hoc.TenLop,
            }
            for _, lop_hoc, status_text, _ in class_statuses
            if status_text == "Đang học"
        ],
        "lopHocs": [
            {
                "lopHocId": lop_hoc.LopHocId,
                "maLop": lop_hoc.MaLop,
                "tenLop": lop_hoc.TenLop,
                "trangThai": status_text,
            }
            for _, lop_hoc, status_text, _ in class_statuses
        ],
    }


def _student_status_payload(
    db: Session,
    student: NguoiDung,
    class_filter: int | None = None,
    visible_class_ids: set[int] | None = None,
) -> dict:
    conversion = (
        db.query(TuyenSinhLeadChuyenDoi)
        .filter(TuyenSinhLeadChuyenDoi.NguoiDungId == student.NguoiDungId)
        .first()
    )
    enrollments = (
        db.query(LopHocHocVien, LopHoc)
        .join(LopHoc, LopHoc.LopHocId == LopHocHocVien.LopHocId)
        .filter(LopHocHocVien.HocVienId == student.NguoiDungId)
        .order_by(LopHoc.NamHoc.desc(), LopHoc.MaLop)
        .all()
    )
    actions = (
        db.query(StudentEnrollmentAction)
        .filter(StudentEnrollmentAction.HocVienId == student.NguoiDungId)
        .order_by(
            StudentEnrollmentAction.NgayHieuLuc,
            StudentEnrollmentAction.ActionId,
        )
        .all()
    )
    role_ids = {
        role_id
        for (role_id,) in db.query(NguoiDungVaiTro.VaiTroId)
        .filter(NguoiDungVaiTro.NguoiDungId == student.NguoiDungId)
        .all()
    }
    return _student_status_payload_from_records(
        student,
        conversion,
        enrollments,
        actions,
        role_ids,
        class_filter,
        visible_class_ids,
    )


@router.get(
    "/rooms",
    dependencies=[Depends(require_permission("CLASS_VIEW"))],
)
def list_rooms(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    query = db.query(PhongHoc)
    if not include_inactive:
        query = query.filter(PhongHoc.TrangThai == "Đang hoạt động")
    return [
        _room_payload(room)
        for room in query.order_by(PhongHoc.MaPhong).all()
    ]


@router.post(
    "/rooms",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CLASS_CREATE"))],
)
def create_room(request: RoomCreate, db: Session = Depends(get_db)):
    room = PhongHoc(
        MaPhong=request.ma_phong,
        TenPhong=request.ten_phong,
        SucChua=request.suc_chua,
        TrangThai="Đang hoạt động",
    )
    db.add(room)
    _commit(db, "Mã phòng đã tồn tại hoặc dữ liệu phòng không hợp lệ.")
    db.refresh(room)
    return _room_payload(room)


@router.get(
    "/classes",
    dependencies=[Depends(require_permission("CLASS_VIEW"))],
)
def list_classes(
    include_inactive: bool = Query(default=False),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [
        _class_payload(db, lop_hoc)
        for lop_hoc in accessible_classes(
            db,
            current_user,
            include_inactive=include_inactive,
        )
    ]


@router.get(
    "/class-options",
    dependencies=[Depends(require_permission("CLASS_UPDATE"))],
)
def get_class_options(db: Session = Depends(get_db)):
    teachers = (
        db.query(NguoiDung)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(
            NguoiDungVaiTro.VaiTroId.in_(TEACHING_ROLE_IDS),
            NguoiDung.TrangThai == "HoatDong",
        )
        .order_by(NguoiDung.HoTen)
        .all()
    )
    students = (
        db.query(NguoiDung)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(
            NguoiDungVaiTro.VaiTroId == STUDENT_ROLE_ID,
            NguoiDung.TrangThai == "HoatDong",
        )
        .order_by(NguoiDung.HoTen)
        .all()
    )
    subjects = (
        db.query(MonHoc)
        .filter(MonHoc.TrangThai == "Đang hoạt động")
        .order_by(MonHoc.MaMonHoc)
        .all()
    )
    rooms = (
        db.query(PhongHoc)
        .filter(PhongHoc.TrangThai == "Đang hoạt động")
        .order_by(PhongHoc.MaPhong)
        .all()
    )
    return {
        "giangViens": [
            {
                "nguoiDungId": user.NguoiDungId,
                "hoTen": user.HoTen,
                "email": user.Email,
                "vaiTroIds": sorted(user_role_ids(db, user.NguoiDungId)),
            }
            for user in teachers
        ],
        "hocViens": [
            {
                "nguoiDungId": user.NguoiDungId,
                "hoTen": user.HoTen,
                "email": user.Email,
            }
            for user in students
        ],
        "monHocs": [
            {
                "monHocId": subject.MonHocId,
                "maMonHoc": subject.MaMonHoc,
                "tenMonHoc": subject.TenMonHoc,
                "soTinChi": subject.SoTinChi,
            }
            for subject in subjects
        ],
        "phongHocs": [_room_payload(room) for room in rooms],
    }


@router.post(
    "/classes",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CLASS_CREATE"))],
)
def create_class(
    request: ClassWrite,
    db: Session = Depends(get_db),
):
    lop_hoc = LopHoc(
        MaLop=request.ma_lop.strip(),
        TenLop=request.ten_lop.strip(),
        NamHoc=request.nam_hoc,
        ChuongTrinhId=request.chuong_trinh_id,
        NgayKhaiGiang=request.ngay_khai_giang,
        SiSoToiDa=request.si_so_toi_da,
        HinhThuc=request.hinh_thuc,
        PhongHocId=request.phong_hoc_id,
        LinkTrucTuyen=request.link_truc_tuyen,
        TienDo=request.tien_do,
        TrangThai="Đang hoạt động",
        NgayTao=datetime.now(),
    )
    if request.chuong_trinh_id is not None:
        program = (
            db.query(ChuongTrinhDaoTao)
            .filter(
                ChuongTrinhDaoTao.ChuongTrinhId == request.chuong_trinh_id
            )
            .first()
        )
        if program is None or program.TrangThai != "Đang áp dụng":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Chỉ được mở lớp bằng chương trình đang áp dụng.",
            )
        lop_hoc.TenLop = program.TenChuongTrinh
    db.add(lop_hoc)
    try:
        db.flush()
        _apply_class_write(db, lop_hoc, request)
        if request.chuong_trinh_id is not None:
            lop_hoc.TenLop = program.TenChuongTrinh
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mã lớp đã tồn tại hoặc dữ liệu lớp bị trùng.",
        ) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except HTTPException:
        db.rollback()
        raise
    _commit(db, "Mã lớp đã tồn tại hoặc dữ liệu lớp bị trùng.")
    return _class_payload(db, lop_hoc)


@router.put(
    "/classes/{class_id}",
    dependencies=[Depends(require_permission("CLASS_UPDATE"))],
)
def update_class(
    class_id: int,
    request: ClassWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lop_hoc = _get_class_or_404(db, class_id)
    _ensure_class_scope(db, current_user, lop_hoc)
    if lop_hoc.TrangThai not in ACTIVE_CLASS_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể chỉnh sửa lớp đã ngừng hoạt động.",
        )
    try:
        _apply_class_write(db, lop_hoc, request)
    except ValueError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except HTTPException:
        db.rollback()
        raise
    _commit(db, "Mã lớp đã tồn tại hoặc dữ liệu lớp bị trùng.")
    return _class_payload(db, lop_hoc)


@router.delete(
    "/classes/{class_id}",
    dependencies=[Depends(require_permission("CLASS_DELETE"))],
)
def archive_class(
    class_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lop_hoc = _get_class_or_404(db, class_id)
    _ensure_class_scope(db, current_user, lop_hoc)
    lop_hoc.TrangThai = "Ngừng hoạt động"
    _commit(db, "Không thể lưu trữ lớp học.")
    return {"message": "Đã lưu trữ lớp học."}


@router.post(
    "/classes/{class_id}/enrollments",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CLASS_UPDATE"))],
)
def enroll_students_in_class(
    class_id: int,
    request: ClassEnrollmentsWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lop_hoc = (
        db.query(LopHoc)
        .filter(LopHoc.LopHocId == class_id)
        .with_for_update()
        .first()
    )
    if lop_hoc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy lớp học.",
        )
    _ensure_class_scope(db, current_user, lop_hoc)
    if lop_hoc.TrangThai == "Ngừng hoạt động":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể ghi danh học viên vào lớp đã ngừng hoạt động.",
        )

    student_ids = request.hoc_vien_ids
    if len(student_ids) != len(set(student_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Danh sách học viên không được trùng lặp.",
        )
    current_ids = {
        student_id
        for (student_id,) in db.query(LopHocHocVien.HocVienId)
        .filter(LopHocHocVien.LopHocId == class_id)
        .all()
    }
    new_ids = [
        student_id
        for student_id in student_ids
        if student_id not in current_ids
    ]
    for student_id in new_ids:
        try:
            ensure_active_student(db, student_id)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
    if len(current_ids) + len(new_ids) > lop_hoc.SiSoToiDa:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sĩ số tối đa của lớp không đủ để ghi danh các học viên đã chọn.",
        )

    now = business_now_naive()
    db.add_all(
        LopHocHocVien(
            LopHocId=class_id,
            HocVienId=student_id,
            NgayThamGia=now,
            NguoiGhiDanhId=current_user.NguoiDungId,
        )
        for student_id in new_ids
    )
    if new_ids:
        _commit(db, "Không thể ghi danh học viên do dữ liệu đã thay đổi.")
    return {
        "daGhiDanh": new_ids,
        "siSoHienTai": len(current_ids) + len(new_ids),
        "siSoToiDa": lop_hoc.SiSoToiDa,
    }


def _training_program_payload(
    db: Session,
    program: ChuongTrinhDaoTao,
) -> dict:
    return {
        "chuongTrinhId": program.ChuongTrinhId,
        "maChuongTrinh": program.MaChuongTrinh,
        "tenChuongTrinh": program.TenChuongTrinh,
        "moTa": program.MoTa,
        "tongThoiLuong": program.TongThoiLuong,
        "hocPhiChuan": float(program.HocPhiChuan),
        "trangThai": program.TrangThai,
        "ngayTao": program.NgayTao,
        "ngayCapNhat": program.NgayCapNhat,
        "soLop": (
            db.query(LopHoc)
            .filter(LopHoc.ChuongTrinhId == program.ChuongTrinhId)
            .count()
        ),
    }


@router.get(
    "/programs",
    dependencies=[Depends(require_permission("CLASS_VIEW"))],
)
def list_training_programs(
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    query = db.query(ChuongTrinhDaoTao)
    if not include_inactive:
        query = query.filter(
            ChuongTrinhDaoTao.TrangThai == "Đang áp dụng"
        )
    return [
        _training_program_payload(db, program)
        for program in query.order_by(ChuongTrinhDaoTao.MaChuongTrinh).all()
    ]


@router.post(
    "/programs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CLASS_CREATE"))],
)
def create_training_program(
    request: TrainingProgramWrite,
    db: Session = Depends(get_db),
):
    program = ChuongTrinhDaoTao(
        MaChuongTrinh=request.ma_chuong_trinh,
        TenChuongTrinh=request.ten_chuong_trinh,
        MoTa=request.mo_ta,
        TongThoiLuong=request.tong_thoi_luong,
        HocPhiChuan=request.hoc_phi_chuan,
        TrangThai=request.trang_thai,
        NgayTao=datetime.now(),
    )
    db.add(program)
    try:
        db.commit()
        db.refresh(program)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mã chương trình đã tồn tại.",
        ) from error
    return _training_program_payload(db, program)


@router.put(
    "/programs/{program_id}",
    dependencies=[Depends(require_permission("CLASS_UPDATE"))],
)
def update_training_program(
    program_id: int,
    request: TrainingProgramWrite,
    db: Session = Depends(get_db),
):
    program = (
        db.query(ChuongTrinhDaoTao)
        .filter(ChuongTrinhDaoTao.ChuongTrinhId == program_id)
        .first()
    )
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy chương trình đào tạo.",
        )

    program.MaChuongTrinh = request.ma_chuong_trinh
    program.TenChuongTrinh = request.ten_chuong_trinh
    program.MoTa = request.mo_ta
    program.TongThoiLuong = request.tong_thoi_luong
    program.HocPhiChuan = request.hoc_phi_chuan
    program.TrangThai = request.trang_thai
    program.NgayCapNhat = datetime.now()
    try:
        db.commit()
        db.refresh(program)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mã chương trình đã tồn tại.",
        ) from error
    return _training_program_payload(db, program)


@router.delete(
    "/programs/{program_id}",
    dependencies=[Depends(require_permission("CLASS_DELETE"))],
)
def delete_training_program(
    program_id: int,
    db: Session = Depends(get_db),
):
    program = (
        db.query(ChuongTrinhDaoTao)
        .filter(ChuongTrinhDaoTao.ChuongTrinhId == program_id)
        .first()
    )
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy chương trình đào tạo.",
        )
    if (
        db.query(LopHoc.LopHocId)
        .filter(LopHoc.ChuongTrinhId == program_id)
        .first()
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Chương trình đã được gắn với lớp học nên không thể xóa. "
                "Hãy ngừng áp dụng chương trình để giữ lịch sử lớp."
            ),
        )
    db.delete(program)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Chương trình đã được gắn với lớp học nên không thể xóa. "
                "Hãy ngừng áp dụng chương trình để giữ lịch sử lớp."
            ),
        ) from error
    return {"message": "Đã xóa chương trình đào tạo."}


def _get_program_or_404(db: Session, program_id: int) -> ChuongTrinhDaoTao:
    program = (
        db.query(ChuongTrinhDaoTao)
        .filter(ChuongTrinhDaoTao.ChuongTrinhId == program_id)
        .first()
    )
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy chương trình đào tạo.",
        )
    return program


def _program_subject_payloads(
    db: Session,
    program_id: int,
) -> list[dict]:
    rows = (
        db.query(ProgramSubject, MonHoc)
        .join(MonHoc, MonHoc.MonHocId == ProgramSubject.MonHocId)
        .filter(ProgramSubject.ChuongTrinhId == program_id)
        .order_by(ProgramSubject.ThuTu)
        .all()
    )
    row_by_membership_id = {
        membership.ChuongTrinhMonHocId: (membership, subject)
        for membership, subject in rows
    }
    prerequisites = (
        db.query(ProgramSubjectPrerequisite)
        .filter(
            ProgramSubjectPrerequisite.ChuongTrinhMonHocId.in_(
                row_by_membership_id
            )
        )
        .all()
        if row_by_membership_id
        else []
    )
    prerequisite_subject_ids = {}
    for item in prerequisites:
        required = row_by_membership_id.get(item.MonTienQuyetId)
        if required is not None:
            prerequisite_subject_ids[item.ChuongTrinhMonHocId] = required[1].MonHocId
    session_rows = (
        db.query(ProgramSession)
        .filter(
            ProgramSession.ChuongTrinhMonHocId.in_(row_by_membership_id)
        )
        .order_by(ProgramSession.ChuongTrinhMonHocId, ProgramSession.SoThuTu)
        .all()
        if row_by_membership_id
        else []
    )
    sessions_by_membership = {membership_id: [] for membership_id in row_by_membership_id}
    for session in session_rows:
        sessions_by_membership[session.ChuongTrinhMonHocId].append(
            {
                "buoiHocId": session.BuoiHocId,
                "soThuTu": session.SoThuTu,
                "chuDe": session.ChuDe,
                "mucTieu": session.MucTieu or "",
            }
        )
    return [
        {
            "monHocId": subject.MonHocId,
            "maMonHoc": subject.MaMonHoc,
            "tenMonHoc": subject.TenMonHoc,
            "soBuoi": subject.SoBuoi,
            "trongSo": float(subject.TrongSo),
            "moTaChuanDauRa": subject.MoTaChuanDauRa,
            "trangThai": subject.TrangThai,
            "thuTu": membership.ThuTu,
            "monTienQuyetId": prerequisite_subject_ids.get(
                membership.ChuongTrinhMonHocId
            ),
            "sessions": sessions_by_membership[membership.ChuongTrinhMonHocId],
        }
        for membership, subject in rows
    ]


@router.get(
    "/programs/{program_id}/subjects",
    dependencies=[Depends(require_permission("CURRICULUM_VIEW"))],
)
def get_program_subjects(
    program_id: int,
    db: Session = Depends(get_db),
):
    _get_program_or_404(db, program_id)
    return _program_subject_payloads(db, program_id)


@router.put(
    "/programs/{program_id}/subjects",
    dependencies=[Depends(require_permission("CURRICULUM_UPDATE"))],
)
def update_program_subjects(
    program_id: int,
    request: ProgramSubjectsWrite,
    db: Session = Depends(get_db),
):
    _get_program_or_404(db, program_id)
    subject_ids = [item.mon_hoc_id for item in request.subjects]
    order_values = [item.thu_tu for item in request.subjects]
    prerequisite_ids = [
        item.mon_tien_quyet_id
        for item in request.subjects
        if item.mon_tien_quyet_id is not None
    ]
    if len(subject_ids) != len(set(subject_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Danh sách môn học không được trùng lặp.",
        )
    if sorted(order_values) != list(range(1, len(order_values) + 1)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Thứ tự môn học phải liên tục bắt đầu từ 1.",
        )
    if len(prerequisite_ids) != len(set(prerequisite_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mỗi môn tiên quyết chỉ được gắn một lần.",
        )
    requested_subjects = (
        db.query(MonHoc)
        .filter(
            MonHoc.MonHocId.in_(subject_ids),
            MonHoc.TrangThai == "Đang hoạt động",
        )
        .all()
        if subject_ids
        else []
    )
    if len(requested_subjects) != len(subject_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Có môn học không tồn tại hoặc đã ngừng hoạt động.",
        )
    if set(prerequisite_ids) - set(subject_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Môn tiên quyết phải thuộc cùng chương trình.",
        )
    if any(
        item.mon_tien_quyet_id == item.mon_hoc_id
        for item in request.subjects
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Môn học không thể là môn tiên quyết của chính nó.",
        )

    existing = (
        db.query(ProgramSubject)
        .filter(ProgramSubject.ChuongTrinhId == program_id)
        .all()
    )
    existing_by_subject = {item.MonHocId: item for item in existing}
    removed = [
        item for item in existing if item.MonHocId not in set(subject_ids)
    ]
    if removed:
        removed_membership_ids = {
            item.ChuongTrinhMonHocId for item in removed
        }
        db.query(ProgramSession).filter(
            ProgramSession.ChuongTrinhMonHocId.in_(removed_membership_ids)
        ).delete(synchronize_session=False)
        db.query(ProgramSubjectPrerequisite).filter(
            (ProgramSubjectPrerequisite.ChuongTrinhMonHocId.in_(removed_membership_ids))
            | (ProgramSubjectPrerequisite.MonTienQuyetId.in_(removed_membership_ids))
        ).delete(synchronize_session=False)
        for item in removed:
            db.delete(item)
        db.flush()

    offset = max((item.ThuTu for item in existing), default=0) + len(subject_ids) + 1
    for item in existing:
        if item not in removed:
            item.ThuTu += offset
    db.flush()
    for request_item in request.subjects:
        membership = existing_by_subject.get(request_item.mon_hoc_id)
        if membership is None:
            membership = ProgramSubject(
                ChuongTrinhId=program_id,
                MonHocId=request_item.mon_hoc_id,
                ThuTu=request_item.thu_tu,
            )
            db.add(membership)
            existing_by_subject[request_item.mon_hoc_id] = membership
        else:
            membership.ThuTu = request_item.thu_tu
    db.flush()

    db.query(ProgramSubjectPrerequisite).filter(
        ProgramSubjectPrerequisite.ChuongTrinhMonHocId.in_(
            [item.ChuongTrinhMonHocId for item in existing_by_subject.values()]
        )
    ).delete(synchronize_session=False)
    for item in request.subjects:
        if item.mon_tien_quyet_id is None:
            continue
        db.add(
            ProgramSubjectPrerequisite(
                ChuongTrinhMonHocId=existing_by_subject[
                    item.mon_hoc_id
                ].ChuongTrinhMonHocId,
                MonTienQuyetId=existing_by_subject[
                    item.mon_tien_quyet_id
                ].ChuongTrinhMonHocId,
            )
        )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể lưu lộ trình môn học do dữ liệu đã thay đổi.",
        ) from error
    return _program_subject_payloads(db, program_id)


def _program_subject_membership(
    db: Session,
    program_id: int,
    subject_id: int,
) -> tuple[ProgramSubject, MonHoc]:
    row = (
        db.query(ProgramSubject, MonHoc)
        .join(MonHoc, MonHoc.MonHocId == ProgramSubject.MonHocId)
        .filter(
            ProgramSubject.ChuongTrinhId == program_id,
            ProgramSubject.MonHocId == subject_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Môn học không thuộc chương trình này.",
        )
    return row


@router.put(
    "/programs/{program_id}/subjects/{subject_id}/sessions",
    dependencies=[Depends(require_permission("CURRICULUM_UPDATE"))],
)
def update_program_sessions(
    program_id: int,
    subject_id: int,
    request: ProgramSessionsWrite,
    db: Session = Depends(get_db),
):
    _get_program_or_404(db, program_id)
    membership, subject = _program_subject_membership(
        db,
        program_id,
        subject_id,
    )
    orders = [item.so_thu_tu for item in request.sessions]
    if len(request.sessions) > subject.SoBuoi:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Số buổi khai báo vượt quá số buổi của môn học.",
        )
    if sorted(orders) != list(range(1, len(orders) + 1)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Số thứ tự buổi học phải liên tục bắt đầu từ 1.",
        )
    db.query(ProgramSession).filter(
        ProgramSession.ChuongTrinhMonHocId
        == membership.ChuongTrinhMonHocId
    ).delete(synchronize_session=False)
    db.add_all(
        ProgramSession(
            ChuongTrinhMonHocId=membership.ChuongTrinhMonHocId,
            SoThuTu=item.so_thu_tu,
            ChuDe=item.chu_de,
            MucTieu=item.muc_tieu,
        )
        for item in request.sessions
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể lưu buổi học do dữ liệu đã thay đổi.",
        ) from error
    return _program_subject_payloads(db, program_id)


@router.post(
    "/programs/{program_id}/subjects/{subject_id}/sessions/clone",
    dependencies=[Depends(require_permission("CURRICULUM_UPDATE"))],
)
def clone_program_sessions(
    program_id: int,
    subject_id: int,
    request: ProgramSessionsClone,
    db: Session = Depends(get_db),
):
    _get_program_or_404(db, program_id)
    target_membership, target_subject = _program_subject_membership(
        db,
        program_id,
        subject_id,
    )
    source_membership, _ = _program_subject_membership(
        db,
        program_id,
        request.source_subject_id,
    )
    if source_membership.ChuongTrinhMonHocId == target_membership.ChuongTrinhMonHocId:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Không thể sao chép buổi học của cùng một môn.",
        )
    source_sessions = (
        db.query(ProgramSession)
        .filter(
            ProgramSession.ChuongTrinhMonHocId
            == source_membership.ChuongTrinhMonHocId
        )
        .order_by(ProgramSession.SoThuTu)
        .all()
    )
    if len(source_sessions) > target_subject.SoBuoi:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Số buổi nguồn vượt quá số buổi cho phép của môn đích.",
        )
    db.query(ProgramSession).filter(
        ProgramSession.ChuongTrinhMonHocId
        == target_membership.ChuongTrinhMonHocId
    ).delete(synchronize_session=False)
    db.add_all(
        ProgramSession(
            ChuongTrinhMonHocId=target_membership.ChuongTrinhMonHocId,
            SoThuTu=index,
            ChuDe=item.ChuDe,
            MucTieu=item.MucTieu,
        )
        for index, item in enumerate(source_sessions, start=1)
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể nhân bản buổi học do dữ liệu đã thay đổi.",
        ) from error
    return _program_subject_payloads(db, program_id)


@router.get(
    "/subjects",
    dependencies=[Depends(require_permission("CLASS_VIEW"))],
)
def list_subjects(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    query = db.query(MonHoc)
    if not include_inactive:
        query = query.filter(MonHoc.TrangThai == "Đang hoạt động")
    subjects = query.order_by(MonHoc.MaMonHoc).all()
    return [
        {
            "monHocId": subject.MonHocId,
            "maMonHoc": subject.MaMonHoc,
            "tenMonHoc": subject.TenMonHoc,
            "soTinChi": subject.SoTinChi,
            "soBuoi": subject.SoBuoi,
            "trongSo": float(subject.TrongSo),
            "moTaChuanDauRa": subject.MoTaChuanDauRa,
            "trangThai": subject.TrangThai,
            "daApDung": (
                db.query(ProgramSubject.ChuongTrinhMonHocId)
                .filter(ProgramSubject.MonHocId == subject.MonHocId)
                .first()
                is not None
            ),
        }
        for subject in subjects
    ]


@router.post(
    "/subjects",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CLASS_CREATE"))],
)
def create_subject(
    request: SubjectCreate,
    db: Session = Depends(get_db),
):
    if not request.ma_mon_hoc.strip() or not request.ten_mon_hoc.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mã môn học và tên môn học không được để trống.",
        )
    subject = MonHoc(
        MaMonHoc=request.ma_mon_hoc.strip(),
        TenMonHoc=request.ten_mon_hoc.strip(),
        SoTinChi=request.so_tin_chi,
        SoBuoi=request.so_buoi,
        TrongSo=request.trong_so,
        MoTaChuanDauRa=request.mo_ta_chuan_dau_ra,
        TrangThai=request.trang_thai,
    )
    db.add(subject)
    _commit(db, "Mã môn học đã tồn tại.")
    return {
        "monHocId": subject.MonHocId,
        "maMonHoc": subject.MaMonHoc,
        "tenMonHoc": subject.TenMonHoc,
        "soTinChi": subject.SoTinChi,
        "soBuoi": subject.SoBuoi,
        "trongSo": float(subject.TrongSo),
        "moTaChuanDauRa": subject.MoTaChuanDauRa,
        "trangThai": subject.TrangThai,
    }


@router.put(
    "/subjects/{subject_id}",
    dependencies=[Depends(require_permission("CLASS_UPDATE"))],
)
def update_subject(
    subject_id: int,
    request: SubjectUpdate,
    db: Session = Depends(get_db),
):
    subject = db.query(MonHoc).filter(MonHoc.MonHocId == subject_id).first()
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy môn học.",
        )
    if not request.ma_mon_hoc.strip() or not request.ten_mon_hoc.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mã môn học và tên môn học không được để trống.",
        )
    subject.MaMonHoc = request.ma_mon_hoc.strip()
    subject.TenMonHoc = request.ten_mon_hoc.strip()
    subject.SoTinChi = request.so_tin_chi
    subject.SoBuoi = request.so_buoi
    subject.TrongSo = request.trong_so
    subject.MoTaChuanDauRa = request.mo_ta_chuan_dau_ra
    subject.TrangThai = request.trang_thai
    _commit(db, "Mã môn học đã tồn tại.")
    return {
        "monHocId": subject.MonHocId,
        "maMonHoc": subject.MaMonHoc,
        "tenMonHoc": subject.TenMonHoc,
        "soTinChi": subject.SoTinChi,
        "soBuoi": subject.SoBuoi,
        "trongSo": float(subject.TrongSo),
        "moTaChuanDauRa": subject.MoTaChuanDauRa,
        "trangThai": subject.TrangThai,
    }


@router.delete(
    "/subjects/{subject_id}",
    dependencies=[Depends(require_permission("CLASS_DELETE"))],
)
def archive_subject(
    subject_id: int,
    db: Session = Depends(get_db),
):
    subject = db.query(MonHoc).filter(MonHoc.MonHocId == subject_id).first()
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy môn học.",
        )
    subject.TrangThai = "Ngừng hoạt động"
    _commit(db, "Không thể lưu trữ môn học.")
    return {"message": "Đã lưu trữ môn học."}


@router.post(
    "/subjects/{subject_id}/archive",
    dependencies=[Depends(require_permission("CURRICULUM_DELETE"))],
)
def archive_subject_action(
    subject_id: int,
    db: Session = Depends(get_db),
):
    return archive_subject(subject_id, db)


@router.post(
    "/subjects/{subject_id}/activate",
    dependencies=[Depends(require_permission("CURRICULUM_UPDATE"))],
)
def activate_subject(
    subject_id: int,
    db: Session = Depends(get_db),
):
    subject = db.query(MonHoc).filter(MonHoc.MonHocId == subject_id).first()
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy môn học.",
        )
    subject.TrangThai = "Đang hoạt động"
    _commit(db, "Không thể áp dụng lại môn học.")
    return {"message": "Đã áp dụng lại môn học."}


@router.get("/students/statuses")
def list_student_statuses(
    search: str | None = Query(default=None, max_length=255),
    class_id: int | None = Query(default=None, alias="classId", gt=0),
    enrollment_status: str | None = Query(
        default=None,
        alias="enrollmentStatus",
        max_length=50,
    ),
    has_history: bool = Query(default=False, alias="hasHistory"),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_permission_or_admin(db, current_user, "USER_VIEW")
    _ensure_permission_or_admin(db, current_user, "GRADE_VIEW")
    roles = user_role_ids(db, current_user.NguoiDungId)
    wide_scope = has_schedule_wide_scope(db, current_user.NguoiDungId, roles)
    visible_classes = accessible_classes(
        db,
        current_user,
        include_inactive=True,
    )
    visible_class_ids = {item.LopHocId for item in visible_classes}
    if class_id is not None and class_id not in visible_class_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được xem học viên của lớp này.",
        )

    students_query = (
        db.query(NguoiDung)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(NguoiDungVaiTro.VaiTroId == STUDENT_ROLE_ID)
        .distinct()
    )
    if not wide_scope:
        if STUDENT_ROLE_ID in roles:
            students_query = students_query.filter(
                NguoiDung.NguoiDungId == current_user.NguoiDungId
            )
        elif visible_class_ids:
            enrolled_ids = db.query(LopHocHocVien.HocVienId).filter(
                LopHocHocVien.LopHocId.in_(visible_class_ids)
            )
            students_query = students_query.filter(
                NguoiDung.NguoiDungId.in_(enrolled_ids)
            )
        else:
            return {
                "items": [],
                "total": 0,
                "pagination": {"page": page, "limit": limit, "total": 0},
                "classes": [],
            }
    if class_id is not None:
        enrolled_ids = db.query(LopHocHocVien.HocVienId).filter(
            LopHocHocVien.LopHocId == class_id
        )
        students_query = students_query.filter(
            NguoiDung.NguoiDungId.in_(enrolled_ids)
        )

    students = students_query.order_by(NguoiDung.HoTen).all()
    student_ids = {student.NguoiDungId for student in students}
    conversions = {
        item.NguoiDungId: item
        for item in db.query(TuyenSinhLeadChuyenDoi)
        .filter(TuyenSinhLeadChuyenDoi.NguoiDungId.in_(student_ids))
        .all()
    } if student_ids else {}
    enrollments_by_student = {student_id: [] for student_id in student_ids}
    for student_id, enrollment, lop_hoc in (
        db.query(LopHocHocVien.HocVienId, LopHocHocVien, LopHoc)
        .join(LopHoc, LopHoc.LopHocId == LopHocHocVien.LopHocId)
        .filter(LopHocHocVien.HocVienId.in_(student_ids))
        .order_by(LopHoc.NamHoc.desc(), LopHoc.MaLop)
        .all()
        if student_ids
        else []
    ):
        enrollments_by_student[student_id].append((enrollment, lop_hoc))
    actions_by_student = {student_id: [] for student_id in student_ids}
    for action in (
        db.query(StudentEnrollmentAction)
        .filter(StudentEnrollmentAction.HocVienId.in_(student_ids))
        .order_by(
            StudentEnrollmentAction.NgayHieuLuc,
            StudentEnrollmentAction.ActionId,
        )
        .all()
        if student_ids
        else []
    ):
        actions_by_student[action.HocVienId].append(action)
    role_ids_by_student = {student_id: set() for student_id in student_ids}
    for user_id, role_id in (
        db.query(NguoiDungVaiTro.NguoiDungId, NguoiDungVaiTro.VaiTroId)
        .filter(NguoiDungVaiTro.NguoiDungId.in_(student_ids))
        .all()
        if student_ids
        else []
    ):
        role_ids_by_student[user_id].add(role_id)

    normalized_search = (search or "").strip().casefold()
    items = []
    for student in students:
        item = _student_status_payload_from_records(
            student,
            conversions.get(student.NguoiDungId),
            enrollments_by_student[student.NguoiDungId],
            actions_by_student[student.NguoiDungId],
            role_ids_by_student[student.NguoiDungId],
            class_filter=class_id,
            visible_class_ids=None if wide_scope else visible_class_ids,
        )
        if normalized_search and not any(
            normalized_search in str(value or "").casefold()
            for value in (
                student.NguoiDungId,
                item["maHocVien"],
                student.HoTen,
                student.Email,
                student.SoDienThoai,
                *(class_item["maLop"] for class_item in item["lopHocs"]),
                *(class_item["tenLop"] for class_item in item["lopHocs"]),
            )
        ):
            continue
        if enrollment_status and item["trangThaiGhiDanh"] != enrollment_status:
            continue
        if status_filter and student.TrangThai != status_filter:
            continue
        if has_history and not item["lopHocs"]:
            continue
        items.append(item)

    total = len(items)
    start = (page - 1) * limit
    return {
        "items": items[start : start + limit],
        "total": total,
        "pagination": {"page": page, "limit": limit, "total": total},
        "classes": [
            {
                "lopHocId": lop_hoc.LopHocId,
                "maLop": lop_hoc.MaLop,
                "tenLop": lop_hoc.TenLop,
                "trangThai": lop_hoc.TrangThai,
            }
            for lop_hoc in visible_classes
        ],
    }


@router.get("/students/{student_id}")
def get_student_profile(
    student_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_permission_or_admin(db, current_user, "USER_VIEW")
    _ensure_permission_or_admin(db, current_user, "GRADE_VIEW")
    student = (
        db.query(NguoiDung)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(
            NguoiDung.NguoiDungId == student_id,
            NguoiDungVaiTro.VaiTroId == STUDENT_ROLE_ID,
        )
        .first()
    )
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy học viên.",
        )
    if not _student_is_visible(db, current_user, student_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được xem hồ sơ học viên này.",
        )

    roles = user_role_ids(db, current_user.NguoiDungId)
    wide_scope = has_schedule_wide_scope(db, current_user.NguoiDungId, roles)
    is_own_profile = (
        student_id == current_user.NguoiDungId and STUDENT_ROLE_ID in roles
    )
    visible_class_ids = (
        None
        if wide_scope or is_own_profile
        else {
            item.LopHocId
            for item in accessible_classes(
                db,
                current_user,
                include_inactive=True,
            )
        }
    )
    conversion = (
        db.query(TuyenSinhLeadChuyenDoi)
        .filter(TuyenSinhLeadChuyenDoi.NguoiDungId == student_id)
        .first()
    )
    program = (
        db.query(ChuongTrinhDaoTao)
        .filter(
            ChuongTrinhDaoTao.ChuongTrinhId == conversion.ChuongTrinhId
        )
        .first()
        if conversion and conversion.ChuongTrinhId is not None
        else None
    )
    status_payload = _student_status_payload(
        db,
        student,
        visible_class_ids=visible_class_ids,
    )
    class_query = (
        db.query(LopHocHocVien, LopHoc)
        .join(LopHoc, LopHoc.LopHocId == LopHocHocVien.LopHocId)
        .filter(LopHocHocVien.HocVienId == student_id)
    )
    if visible_class_ids is not None:
        class_query = class_query.filter(LopHoc.LopHocId.in_(visible_class_ids))
    classes = class_query.order_by(LopHoc.NamHoc.desc(), LopHoc.MaLop).all()

    action_query = (
        db.query(StudentEnrollmentAction, LopHoc)
        .join(LopHoc, LopHoc.LopHocId == StudentEnrollmentAction.LopHocId)
        .filter(StudentEnrollmentAction.HocVienId == student_id)
    )
    if visible_class_ids is not None:
        action_query = action_query.filter(
            StudentEnrollmentAction.LopHocId.in_(visible_class_ids)
        )
    actions = action_query.order_by(
        StudentEnrollmentAction.NgayHieuLuc.desc(),
        StudentEnrollmentAction.ActionId.desc(),
    ).all()
    action_users = (
        {
            user.NguoiDungId: user.HoTen
            for user in db.query(NguoiDung)
            .filter(
                NguoiDung.NguoiDungId.in_(
                    {action.NguoiThucHienId for action, _ in actions}
                )
            )
            .all()
        }
        if actions
        else {}
    )
    target_class_ids = {
        action.LopHocDichId
        for action, _ in actions
        if action.LopHocDichId is not None
    }
    target_classes = (
        {
            lop_hoc.LopHocId: lop_hoc
            for lop_hoc in db.query(LopHoc)
            .filter(LopHoc.LopHocId.in_(target_class_ids))
            .all()
        }
        if target_class_ids
        else {}
    )
    grade_query = db.query(Diem).filter(Diem.HocVienId == student_id)
    if visible_class_ids is not None:
        grade_query = grade_query.filter(Diem.LopHocId.in_(visible_class_ids))
    grades = grade_query.order_by(
        Diem.NamHoc.desc(),
        Diem.HocKy.desc(),
        Diem.DiemId,
    ).all()
    return {
        "hocVien": {
            "nguoiDungId": student.NguoiDungId,
            "maHocVien": conversion.MaHocVien if conversion else None,
            "hoTen": student.HoTen,
            "email": student.Email,
            "soDienThoai": student.SoDienThoai,
            "ngaySinh": student.NgaySinh.isoformat() if student.NgaySinh else None,
            "diaChi": student.DiaChi,
            "trangThai": student.TrangThai,
            "trinhDoDauVao": student.TrinhDoDauVao,
            "ghiChu": student.GhiChuHoSo,
            "ngayNhapHoc": (
                conversion.NgayNhapHoc.date().isoformat()
                if conversion
                else None
            ),
            "tenChuongTrinh": program.TenChuongTrinh if program else None,
            "trangThaiGhiDanh": status_payload["trangThaiGhiDanh"],
        },
        "lopHocs": [
            {
                "lopHocId": lop_hoc.LopHocId,
                "maLop": lop_hoc.MaLop,
                "tenLop": lop_hoc.TenLop,
                "namHoc": lop_hoc.NamHoc,
                "trangThai": next(
                    (
                        item["trangThai"]
                        for item in status_payload["lopHocs"]
                        if item["lopHocId"] == lop_hoc.LopHocId
                    ),
                    lop_hoc.TrangThai,
                ),
                "tenChuongTrinh": (
                    db.query(ChuongTrinhDaoTao.TenChuongTrinh)
                    .filter(
                        ChuongTrinhDaoTao.ChuongTrinhId
                        == lop_hoc.ChuongTrinhId
                    )
                    .scalar()
                    if lop_hoc.ChuongTrinhId is not None
                    else None
                ),
                "ngayKhaiGiang": lop_hoc.NgayKhaiGiang.isoformat(),
                "ngayGhiDanh": enrollment.NgayThamGia.date().isoformat(),
            }
            for enrollment, lop_hoc in classes
        ],
        "thaoTacs": [
            {
                "actionId": action.ActionId,
                "loaiThaoTac": action.LoaiThaoTac,
                "ngayHieuLuc": action.NgayHieuLuc.isoformat(),
                "lyDo": action.LyDo,
                "maLop": lop_hoc.MaLop,
                "maLopDich": (
                    target_classes[action.LopHocDichId].MaLop
                    if action.LopHocDichId in target_classes
                    else None
                ),
                "nguoiThucHien": action_users.get(action.NguoiThucHienId),
                "ngayTao": action.NgayTao.isoformat(),
            }
            for action, lop_hoc in actions
        ],
        "diems": [_grade_payload(db, grade) for grade in grades],
    }


@router.put("/students/{student_id}")
def update_student_profile(
    student_id: int,
    request: StudentProfileUpdate,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_permission_or_admin(db, current_user, "STUDENT_PROFILE_UPDATE")
    student = (
        db.query(NguoiDung)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(
            NguoiDung.NguoiDungId == student_id,
            NguoiDungVaiTro.VaiTroId == STUDENT_ROLE_ID,
        )
        .first()
    )
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy học viên.",
        )
    student.HoTen = request.ho_ten
    student.Email = request.email
    student.SoDienThoai = request.so_dien_thoai
    student.NgaySinh = request.ngay_sinh
    student.DiaChi = request.dia_chi
    student.TrinhDoDauVao = request.trinh_do_dau_vao
    student.GhiChuHoSo = request.ghi_chu
    _commit(db, "Email đã được sử dụng bởi tài khoản khác.")
    return {"message": "Đã cập nhật hồ sơ học viên."}


@router.post(
    "/classes/{class_id}/students/{student_id}/actions",
    status_code=status.HTTP_201_CREATED,
)
def create_student_enrollment_action(
    class_id: int,
    student_id: int,
    request: StudentEnrollmentActionWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_permission_or_admin(db, current_user, "CLASS_UPDATE")
    source_class = _get_class_or_404(db, class_id)
    _ensure_class_scope(db, current_user, source_class)
    student = (
        db.query(NguoiDung)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(
            NguoiDung.NguoiDungId == student_id,
            NguoiDungVaiTro.VaiTroId == STUDENT_ROLE_ID,
        )
        .with_for_update()
        .first()
    )
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy học viên.",
        )
    enrollment = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == class_id,
            LopHocHocVien.HocVienId == student_id,
        )
        .with_for_update()
        .first()
    )
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Học viên không được ghi danh trong lớp này.",
        )

    today = business_now().date()
    if request.ngay_hieu_luc < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ngày hiệu lực không được nằm trong quá khứ.",
        )
    if request.ngay_hieu_luc < enrollment.NgayThamGia.date():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ngày hiệu lực không được trước ngày ghi danh.",
        )
    latest_action = (
        db.query(StudentEnrollmentAction)
        .filter(
            StudentEnrollmentAction.HocVienId == student_id,
            StudentEnrollmentAction.LopHocId == class_id,
        )
        .order_by(
            StudentEnrollmentAction.NgayHieuLuc.desc(),
            StudentEnrollmentAction.ActionId.desc(),
        )
        .first()
    )
    if latest_action is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Học viên đã có trạng thái kết thúc hoặc bảo lưu trong lớp này.",
        )

    target_class = None
    if request.loai_thao_tac == "ChuyenLop":
        target_class = _get_class_or_404(db, request.lop_hoc_dich_id)
        _ensure_class_scope(db, current_user, target_class)
        if target_class.LopHocId == class_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Lớp đích phải khác lớp hiện tại.",
            )
        if target_class.TrangThai not in {
            "Chuẩn bị",
            "Đang hoạt động",
            "Đang học",
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Không thể chuyển học viên vào lớp đã ngừng hoạt động.",
            )
        duplicate_enrollment = (
            db.query(LopHocHocVien)
            .filter(
                LopHocHocVien.LopHocId == target_class.LopHocId,
                LopHocHocVien.HocVienId == student_id,
            )
            .with_for_update()
            .first()
        )
        if duplicate_enrollment is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Học viên đã được ghi danh trong lớp đích.",
            )
        target_size = (
            db.query(LopHocHocVien)
            .filter(LopHocHocVien.LopHocId == target_class.LopHocId)
            .count()
        )
        if target_size >= target_class.SiSoToiDa:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lớp đích đã đạt sĩ số tối đa.",
            )

    action = StudentEnrollmentAction(
        HocVienId=student_id,
        LopHocId=class_id,
        LopHocDichId=target_class.LopHocId if target_class else None,
        LoaiThaoTac=request.loai_thao_tac,
        NgayHieuLuc=request.ngay_hieu_luc,
        LyDo=request.ly_do,
        NguoiThucHienId=current_user.NguoiDungId,
        NgayTao=business_now_naive(),
    )
    db.add(action)
    if target_class is not None:
        db.add(
            LopHocHocVien(
                LopHocId=target_class.LopHocId,
                HocVienId=student_id,
                NgayThamGia=datetime.combine(
                    request.ngay_hieu_luc,
                    datetime.min.time(),
                ),
                NguoiGhiDanhId=current_user.NguoiDungId,
            )
        )
    _commit(db, "Không thể ghi nhận thao tác học viên do dữ liệu đã thay đổi.")
    return {
        "actionId": action.ActionId,
        "loaiThaoTac": action.LoaiThaoTac,
        "ngayHieuLuc": action.NgayHieuLuc.isoformat(),
        "lyDo": action.LyDo,
        "maLop": source_class.MaLop,
        "maLopDich": target_class.MaLop if target_class else None,
        "nguoiThucHien": current_user.HoTen,
        "ngayTao": action.NgayTao.isoformat(),
    }


@router.get(
    "/grade-options",
    dependencies=[Depends(require_permission("GRADE_VIEW"))],
)
def get_grade_options(
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    classes = accessible_classes(db, current_user)
    roles = user_role_ids(db, current_user.NguoiDungId)
    payload = []
    for lop_hoc in classes:
        student_query = (
            db.query(NguoiDung)
            .join(
                LopHocHocVien,
                LopHocHocVien.HocVienId == NguoiDung.NguoiDungId,
            )
            .filter(LopHocHocVien.LopHocId == lop_hoc.LopHocId)
        )
        if (
            2 in roles
            and not roles.intersection({3, 7, 8})
        ):
            student_query = student_query.filter(
                NguoiDung.NguoiDungId == current_user.NguoiDungId
            )
        students = student_query.order_by(NguoiDung.HoTen).all()
        subjects = (
            db.query(MonHoc)
            .join(
                LopHocMonHoc,
                LopHocMonHoc.MonHocId == MonHoc.MonHocId,
            )
            .filter(
                LopHocMonHoc.LopHocId == lop_hoc.LopHocId,
                MonHoc.TrangThai == "Đang hoạt động",
            )
            .order_by(MonHoc.MaMonHoc)
            .all()
        )
        payload.append(
            {
                "lopHocId": lop_hoc.LopHocId,
                "maLop": lop_hoc.MaLop,
                "tenLop": lop_hoc.TenLop,
                "hocViens": [
                    {
                        "nguoiDungId": student.NguoiDungId,
                        "hoTen": student.HoTen,
                        "email": student.Email,
                    }
                    for student in students
                ],
                "monHocs": [
                    {
                        "monHocId": subject.MonHocId,
                        "maMonHoc": subject.MaMonHoc,
                        "tenMonHoc": subject.TenMonHoc,
                    }
                    for subject in subjects
                ],
            }
        )
    return {"classes": payload}


@router.get(
    "/grades",
    dependencies=[Depends(require_permission("GRADE_VIEW"))],
)
def list_grades(
    lop_hoc_id: int | None = Query(default=None, alias="lopHocId", gt=0),
    mon_hoc_id: int | None = Query(default=None, alias="monHocId", gt=0),
    hoc_ky: int | None = Query(default=None, alias="hocKy", ge=1, le=3),
    nam_hoc: str | None = Query(default=None, alias="namHoc", min_length=9, max_length=9),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = accessible_grades_query(db, current_user)
    if lop_hoc_id is not None:
        query = query.filter(Diem.LopHocId == lop_hoc_id)
    if mon_hoc_id is not None:
        query = query.filter(Diem.MonHocId == mon_hoc_id)
    if hoc_ky is not None:
        query = query.filter(Diem.HocKy == hoc_ky)
    if nam_hoc is not None:
        query = query.filter(Diem.NamHoc == nam_hoc)
    grades = query.order_by(Diem.NamHoc.desc(), Diem.HocKy, Diem.DiemId).all()
    return [_grade_payload(db, grade) for grade in grades]


@router.post(
    "/grades",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("GRADE_CREATE"))],
)
def create_grade(
    request: GradeWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_grade_scope(db, current_user, request)
    grade = Diem(
        LopHocId=request.lop_hoc_id,
        HocVienId=request.hoc_vien_id,
        MonHocId=request.mon_hoc_id,
        HocKy=request.hoc_ky,
        NamHoc=request.nam_hoc,
        DiemQuaTrinh=request.diem_qua_trinh,
        DiemGiuaKy=request.diem_giua_ky,
        DiemCuoiKy=request.diem_cuoi_ky,
        NgayTao=datetime.now(),
        NgayCapNhat=datetime.now(),
    )
    db.add(grade)
    _commit(db, "Bảng điểm này đã tồn tại hoặc dữ liệu không hợp lệ.")
    return _grade_payload(db, grade)


@router.put(
    "/grades/{grade_id}",
    dependencies=[Depends(require_permission("GRADE_UPDATE"))],
)
def update_grade(
    grade_id: int,
    request: GradeWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    grade = db.query(Diem).filter(Diem.DiemId == grade_id).first()
    if grade is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bảng điểm.",
        )
    existing_class = _get_class_or_404(db, grade.LopHocId)
    _ensure_class_scope(db, current_user, existing_class)
    if (
        request.lop_hoc_id != grade.LopHocId
        or request.hoc_vien_id != grade.HocVienId
        or request.mon_hoc_id != grade.MonHocId
        or request.hoc_ky != grade.HocKy
        or request.nam_hoc != grade.NamHoc
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Không thể chuyển bảng điểm sang học viên, lớp, môn hoặc học kỳ khác.",
        )
    _validate_grade_scope(db, current_user, request)
    grade.LopHocId = request.lop_hoc_id
    grade.HocVienId = request.hoc_vien_id
    grade.MonHocId = request.mon_hoc_id
    grade.HocKy = request.hoc_ky
    grade.NamHoc = request.nam_hoc
    grade.DiemQuaTrinh = request.diem_qua_trinh
    grade.DiemGiuaKy = request.diem_giua_ky
    grade.DiemCuoiKy = request.diem_cuoi_ky
    grade.NgayCapNhat = datetime.now()
    _commit(db, "Bảng điểm này đã tồn tại hoặc dữ liệu không hợp lệ.")
    return _grade_payload(db, grade)


@router.delete(
    "/grades/{grade_id}",
    dependencies=[Depends(require_permission("GRADE_DELETE"))],
)
def delete_grade(
    grade_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    grade = db.query(Diem).filter(Diem.DiemId == grade_id).first()
    if grade is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bảng điểm.",
        )
    lop_hoc = _get_class_or_404(db, grade.LopHocId)
    _ensure_class_scope(db, current_user, lop_hoc)
    db.delete(grade)
    _commit(db, "Không thể xóa bảng điểm.")
    return {"message": "Đã xóa bảng điểm."}
