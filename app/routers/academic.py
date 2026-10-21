from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.diem import Diem
from app.models.admissions import LeadConversion
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.curriculum import (
    ProgramSession,
    ProgramSubject,
    ProgramSubjectPrerequisite,
)
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import (
    LopHocHocVien,
    LopHocHocVienThaoTac,
)
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.mon_hoc import MonHoc
from app.models.phong_hoc import PhongHoc
from app.models.program_subject import (
    BuoiHoc,
    ChuongTrinhMonHoc,
    ChuongTrinhMonHocTienQuyet,
)
from app.models.quyen import Quyen
from app.models.student_enrollment_action import StudentEnrollmentAction
from app.models.tuyen_sinh_lead_chuyen_doi import TuyenSinhLeadChuyenDoi
from app.models.vai_tro_quyen import VaiTroQuyen
from app.schemas.academic import (
    ClassEnrollmentWrite,
    ClassEnrollmentsWrite,
    ClassStudentActionWrite,
    ClassWrite,
    GradeWrite,
    RoomCreate,
    RoomWrite,
    StudentEnrollmentActionWrite,
    StudentProfileWrite,
    StudentProfileUpdate,
    SubjectCreate,
    SubjectUpdate,
    TrainingProgramWrite,
)
from app.schemas.curriculum import (
    ProgramSubjectsWrite,
    SessionCloneWrite,
    SessionsWrite,
    ProgramSessionsClone,
    ProgramSessionsWrite,
)
from app.services.academic_service import (
    ACTIVE_CLASS_STATUSES,
    INSTRUCTOR_ROLE_ID,
    ASSISTANT_ROLE_ID,
    TEACHING_ROLE_IDS,
    STUDENT_ROLE_ID,
    TEACHING_ASSISTANT_ROLE_ID,
    TEACHING_ROLE_IDS,
    accessible_classes,
    accessible_grades_query,
    build_prerequisite_map,
    can_access_class,
    ensure_active_teaching_role,
    ensure_active_instructor,
    ensure_active_student,
    ensure_active_subjects,
    ensure_valid_academic_year,
    user_is_admin,
    has_schedule_wide_scope,
    user_role_ids,
)
from app.services.business_time import business_now, business_now_naive


router = APIRouter(prefix="/academic", tags=["Academic management"])
CLASS_STATUS_TRANSITIONS = {
    "Chuẩn bị": {"Đang học", "Hủy"},
    "Đang học": {"Kết thúc", "Hủy"},
    "Đang hoạt động": {"Đang học", "Kết thúc", "Hủy"},
    "Kết thúc": set(),
    "Hủy": set(),
}
ACTIVE_CLASS_STATUSES = {"Chuẩn bị", "Đang học", "Đang hoạt động"}
ENROLLMENT_STATUS_CLASS_FILTERS = {
    "Đang học": {"Đang học", "Đang hoạt động"},
    "Sắp bắt đầu": {"Chuẩn bị"},
    "Đã kết thúc": {"Kết thúc"},
    "Đã hủy": {"Hủy"},
}


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
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
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
        .filter(
            LopHocHocVien.LopHocId == lop_hoc.LopHocId,
            LopHocHocVien.NgayThamGia <= today_end,
            (LopHocHocVien.NgayKetThuc.is_(None))
            | (LopHocHocVien.NgayKetThuc > today_start),
        )
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
    enrollment_rows = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == lop_hoc.LopHocId,
            LopHocHocVien.NgayThamGia <= today_end,
            (LopHocHocVien.NgayKetThuc.is_(None))
            | (LopHocHocVien.NgayKetThuc > today_start),
        )
        .all()
    )
    enrollment_by_student = {
        row.HocVienId: row for row in enrollment_rows
    }
    enrollment_user_ids = {
        row.NguoiGhiDanhId for row in enrollment_rows
        if row.NguoiGhiDanhId is not None
    }
    enrollment_users = {
        user.NguoiDungId: user.HoTen
        for user in db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId.in_(enrollment_user_ids))
        .all()
    } if enrollment_user_ids else {}
    teaching_rows = (
        db.query(LopHocMonHocGiangVien)
        .filter(LopHocMonHocGiangVien.LopHocId == lop_hoc.LopHocId)
        .order_by(
            LopHocMonHocGiangVien.MonHocId,
            LopHocMonHocGiangVien.VaiTro,
            LopHocMonHocGiangVien.GiangVienId,
        )
        .all()
    )
    assignments = teaching_rows
    assigned_teacher_ids = {item.GiangVienId for item in teaching_rows}
    assigned_teachers = {
        teacher.NguoiDungId: teacher
        for teacher in db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId.in_(assigned_teacher_ids))
        .all()
    } if assigned_teacher_ids else {}
    assignments_by_subject: dict[int, list[dict]] = {}
    for assignment in teaching_rows:
        teacher = assigned_teachers.get(assignment.GiangVienId)
        if teacher is not None:
            assignments_by_subject.setdefault(assignment.MonHocId, []).append(
                {
                    "giangVienId": teacher.NguoiDungId,
                    "hoTen": teacher.HoTen,
                    "email": teacher.Email,
                    "vaiTro": assignment.VaiTro,
                }
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
        "loaiPhong": room.LoaiPhong if room else None,
        "canhBaoSucChuaPhong": (
            room is not None and len(students) > room.SucChua
        ),
        "linkTrucTuyen": lop_hoc.LinkTrucTuyen,
        "tienDo": float(lop_hoc.TienDo or 0),
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
                "ngayGhiDanh": enrollment_by_student[student.NguoiDungId].NgayThamGia,
                "nguoiGhiDanh": enrollment_users.get(
                    enrollment_by_student[student.NguoiDungId].NguoiGhiDanhId
                ),
            }
            for student in students
        ],
        "monHocIds": [subject.MonHocId for subject in subjects],
        "monHocs": [
            {
                **_subject_option(subject),
                "giangViens": assignments_by_subject.get(subject.MonHocId, []),
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
        "loaiPhong": room.LoaiPhong,
        "trangThai": room.TrangThai,
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
    actor_id: int | None = None,
) -> None:
    if not request.ma_lop.strip() or not request.ten_lop.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Mã lớp và tên lớp không được để trống.",
        )
    ensure_valid_academic_year(request.nam_hoc)
    if request.trang_thai != lop_hoc.TrangThai and request.trang_thai not in (
        CLASS_STATUS_TRANSITIONS.get(lop_hoc.TrangThai, set())
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Không thể chuyển trạng thái lớp từ “{lop_hoc.TrangThai}” sang “{request.trang_thai}”.",
        )
    if request.trang_thai == "Kết thúc" and request.tien_do < 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cần hoàn thành 100% tiến độ trước khi kết thúc lớp.",
        )
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
    if len(student_ids) > request.si_so_toi_da:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Số học viên vượt quá sĩ số tối đa của lớp.",
        )
    if request.phong_hoc_id is not None:
        room = (
            db.query(PhongHoc)
            .filter(PhongHoc.PhongHocId == request.phong_hoc_id)
            .first()
        )
        if room is None or room.TrangThai != "Đang hoạt động":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Phòng học không tồn tại hoặc đã ngừng hoạt động.",
            )
        expected_room_type = (
            "Trực tuyến"
            if request.hinh_thuc == "Trực tuyến"
            else "Trực tiếp"
        )
        if room.LoaiPhong != expected_room_type:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Loại phòng không phù hợp với hình thức học của lớp.",
            )
        if len(student_ids) > room.SucChua:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Số học viên vượt quá sức chứa của phòng học.",
            )
    if request.hinh_thuc == "Trực tuyến" and not request.link_truc_tuyen:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Lớp trực tuyến cần có liên kết học trực tuyến.",
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
            for assignment in request.phan_cong_giang_vien or []:
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
        for assignment in request.phan_cong_giang_vien or []:
            required_role_id = (
                INSTRUCTOR_ROLE_ID
                if assignment.vai_tro == "Chính"
                else ASSISTANT_ROLE_ID
            )
            ensure_active_teaching_role(
                db,
                assignment.giang_vien_id,
                required_role_id,
            )
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
    requested_assignments = [
        (
            item.mon_hoc_id,
            item.giang_vien_id,
            item.vai_tro,
        )
        for item in request.phan_cong_giang_vien or []
    ]
    if request.giang_vien_id is not None:
        primary_subject_ids = {
            subject_id
            for subject_id, _, role in requested_assignments
            if role == "Chính"
        }
        requested_assignments.extend(
            (subject_id, request.giang_vien_id, "Chính")
            for subject_id in request.mon_hoc_ids
            if subject_id not in primary_subject_ids
        )
    if len({(subject_id, teacher_id) for subject_id, teacher_id, _ in requested_assignments}) != len(requested_assignments):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Không được phân công trùng giảng viên cho cùng một môn.",
        )
    if any(subject_id not in set(request.mon_hoc_ids) for subject_id, _, _ in requested_assignments):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Chỉ được phân công giảng viên cho môn học đã gắn với lớp.",
        )
    for subject_id in request.mon_hoc_ids:
        subject_assignments = [
            role for assigned_subject, _, role in requested_assignments
            if assigned_subject == subject_id
        ]
        if subject_assignments.count("Chính") != 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Mỗi môn học của lớp cần đúng một giảng viên chính.",
            )
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
    primary_teacher_ids = [
        teacher_id
        for _, teacher_id, role in requested_assignments
        if role == "Chính"
    ]
    lop_hoc.GiangVienId = (
        primary_teacher_ids[0]
        if primary_teacher_ids
        else request.giang_vien_id
    )
    lop_hoc.NgayKhaiGiang = request.ngay_khai_giang
    lop_hoc.SiSoToiDa = request.si_so_toi_da
    lop_hoc.HinhThuc = request.hinh_thuc
    lop_hoc.PhongHocId = request.phong_hoc_id
    lop_hoc.LinkTrucTuyen = request.link_truc_tuyen
    lop_hoc.TienDo = request.tien_do
    lop_hoc.TrangThai = request.trang_thai

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
                NguoiGhiDanhId=actor_id,
            )
        )

    db.query(LopHocMonHocGiangVien).filter(
        LopHocMonHocGiangVien.LopHocId == lop_hoc.LopHocId
    ).delete(synchronize_session=False)
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
    db.add_all(
        [
            LopHocMonHocGiangVien(
                LopHocId=lop_hoc.LopHocId,
                MonHocId=subject_id,
                GiangVienId=teacher_id,
                VaiTro=role,
            )
            for subject_id, teacher_id, role in requested_assignments
        ]
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
        LoaiPhong=request.loai_phong,
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
    status_filter: str | None = Query(default=None, alias="status"),
    program_id: int | None = Query(default=None, alias="programId", gt=0),
    instructor_id: int | None = Query(default=None, alias="instructorId", gt=0),
    start_date: date | None = Query(default=None, alias="startDate"),
    end_date: date | None = Query(default=None, alias="endDate"),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ngày bắt đầu lọc không được sau ngày kết thúc.",
        )
    classes = accessible_classes(
        db,
        current_user,
        include_inactive=include_inactive,
    )
    if status_filter:
        classes = [item for item in classes if item.TrangThai == status_filter]
    if program_id is not None:
        classes = [item for item in classes if item.ChuongTrinhId == program_id]
    if start_date:
        classes = [
            item for item in classes
            if item.NgayKhaiGiang is not None and item.NgayKhaiGiang >= start_date
        ]
    if end_date:
        classes = [
            item for item in classes
            if item.NgayKhaiGiang is not None and item.NgayKhaiGiang <= end_date
        ]
    if instructor_id is not None:
        class_ids = {
            class_id
            for (class_id,) in db.query(LopHocMonHocGiangVien.LopHocId)
            .filter(LopHocMonHocGiangVien.GiangVienId == instructor_id)
            .all()
        }
        classes = [
            item for item in classes
            if item.GiangVienId == instructor_id or item.LopHocId in class_ids
        ]
    return [_class_payload(db, item) for item in classes]


@router.put(
    "/rooms/{room_id}",
    dependencies=[Depends(require_permission("CLASS_UPDATE"))],
)
def update_room(room_id: int, request: RoomWrite, db: Session = Depends(get_db)):
    room = db.query(PhongHoc).filter(PhongHoc.PhongHocId == room_id).first()
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phòng học.",
        )
    room.MaPhong = request.ma_phong
    room.TenPhong = request.ten_phong
    room.SucChua = request.suc_chua
    room.LoaiPhong = request.loai_phong
    for lop_hoc in (
        db.query(LopHoc)
        .filter(LopHoc.PhongHocId == room_id)
        .all()
    ):
        enrolled_count = (
            db.query(LopHocHocVien)
            .filter(LopHocHocVien.LopHocId == lop_hoc.LopHocId)
            .count()
        )
        expected_room_type = (
            "Trực tuyến"
            if lop_hoc.HinhThuc == "Trực tuyến"
            else "Trực tiếp"
        )
        if enrolled_count > room.SucChua or room.LoaiPhong != expected_room_type:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sức chứa hoặc loại phòng không phù hợp với lớp đang sử dụng.",
            )
    _commit(db, "Mã phòng đã tồn tại hoặc thông tin phòng không hợp lệ.")
    return {
        "phongHocId": room.PhongHocId,
        "maPhong": room.MaPhong,
        "tenPhong": room.TenPhong,
        "sucChua": room.SucChua,
        "loaiPhong": room.LoaiPhong,
        "trangThai": room.TrangThai,
    }


@router.delete(
    "/rooms/{room_id}",
    dependencies=[Depends(require_permission("CLASS_DELETE"))],
)
def archive_room(room_id: int, db: Session = Depends(get_db)):
    room = db.query(PhongHoc).filter(PhongHoc.PhongHocId == room_id).first()
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phòng học.",
        )
    if db.query(LopHoc.LopHocId).filter(LopHoc.PhongHocId == room_id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể ngừng phòng đang được gán cho lớp.",
        )
    room.TrangThai = "Ngừng hoạt động"
    _commit(db, "Không thể ngừng hoạt động phòng học.")
    return {"message": "Đã ngừng hoạt động phòng học."}


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
                        "vaiTroIds": sorted(user_role_ids(db, user.NguoiDungId) & TEACHING_ROLE_IDS),
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
            _subject_option_with_credit(subject)
            for subject in subjects
        ],
        "phongHocs": [
            {**_room_payload(room), "loaiPhong": room.LoaiPhong}
            for room in rooms
        ],
    }


@router.post(
    "/classes",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CLASS_CREATE"))],
)
def create_class(
    request: ClassWrite,
    db: Session = Depends(get_db),
    current_user: NguoiDung = Depends(get_current_user),
):
    if request.trang_thai != "Chuẩn bị":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Lớp mới phải bắt đầu ở trạng thái Chuẩn bị.",
        )
    lop_hoc = LopHoc(
        MaLop=request.ma_lop.strip(),
        TenLop=request.ten_lop.strip(),
        NamHoc=request.nam_hoc,
        ChuongTrinhId=request.chuong_trinh_id,
        TrangThai=request.trang_thai,
        NgayTao=datetime.now(),
        NgayKhaiGiang=request.ngay_khai_giang,
        SiSoToiDa=request.si_so_toi_da,
        HinhThuc=request.hinh_thuc,
        PhongHocId=request.phong_hoc_id,
        LinkTrucTuyen=request.link_truc_tuyen,
        TienDo=request.tien_do,
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
        _apply_class_write(
            db,
            lop_hoc,
            request,
            actor_id=(
                current_user.NguoiDungId
                if isinstance(current_user, NguoiDung)
                else None
            ),
        )
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
    if lop_hoc.TrangThai not in {"Chuẩn bị", "Đang học", "Đang hoạt động"}:
        if lop_hoc.TrangThai in {"Ngừng hoạt động", "Kết thúc", "Hủy"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Không thể chỉnh sửa lớp đã kết thúc, hủy hoặc lưu trữ.",
            )
    try:
        _apply_class_write(
            db,
            lop_hoc,
            request,
            actor_id=current_user.NguoiDungId,
        )
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


@router.post(
    "/classes/{class_id}/enrollments/strict",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CLASS_UPDATE"))],
)
def enroll_students(
    class_id: int,
    request: ClassEnrollmentWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lop_hoc = _get_class_or_404(db, class_id)
    _ensure_class_scope(db, current_user, lop_hoc)
    if lop_hoc.TrangThai not in {"Chuẩn bị", "Đang học", "Đang hoạt động"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chỉ được ghi danh vào lớp đang chuẩn bị hoặc đang học.",
        )
    existing_ids = {
        row.HocVienId
        for row in db.query(LopHocHocVien.HocVienId)
        .filter(LopHocHocVien.LopHocId == lop_hoc.LopHocId)
        .all()
    }
    already_enrolled_ids = existing_ids.intersection(request.hoc_vien_ids)
    if already_enrolled_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Một hoặc nhiều học viên đã được ghi danh trong lớp. "
                "Tải lại danh sách và chọn học viên khác."
            ),
        )
    new_ids = set(request.hoc_vien_ids) - existing_ids
    room = (
        db.query(PhongHoc)
        .filter(PhongHoc.PhongHocId == lop_hoc.PhongHocId)
        .first()
        if lop_hoc.PhongHocId is not None
        else None
    )
    effective_capacity = min(
        lop_hoc.SiSoToiDa,
        room.SucChua if room is not None else lop_hoc.SiSoToiDa,
    )
    if len(existing_ids) + len(new_ids) > effective_capacity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Số học viên vượt quá sĩ số tối đa của lớp hoặc sức chứa phòng.",
        )
    try:
        for student_id in sorted(new_ids):
            ensure_active_student(db, student_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    now = datetime.now()
    db.add_all(
        [
            LopHocHocVien(
                LopHocId=lop_hoc.LopHocId,
                HocVienId=student_id,
                NgayThamGia=now,
                NguoiGhiDanhId=current_user.NguoiDungId,
            )
            for student_id in sorted(new_ids)
        ]
    )
    _commit(db, "Không thể ghi danh học viên vào lớp.")
    return {
        "lopHocId": class_id,
        "daGhiDanh": sorted(new_ids),
        "daCoTrongLop": sorted(existing_ids & set(request.hoc_vien_ids)),
        "siSoHienTai": len(existing_ids) + len(new_ids),
        "siSoToiDa": lop_hoc.SiSoToiDa,
    }


@router.post(
    "/classes/{class_id}/students/{student_id}/actions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CLASS_UPDATE"))],
)
def create_student_class_action(
    class_id: int,
    student_id: int,
    request: ClassStudentActionWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = user_role_ids(db, current_user.NguoiDungId)
    if not user_is_admin(db, current_user.NguoiDungId) and 7 not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ quản lý đào tạo hoặc quản trị viên mới được xử lý học viên.",
        )

    source_class = _get_class_or_404(db, class_id)
    if source_class.TrangThai not in ACTIVE_CLASS_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể xử lý học viên trong lớp đã kết thúc hoặc bị hủy.",
        )
    enrollment = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == class_id,
            LopHocHocVien.HocVienId == student_id,
            LopHocHocVien.NgayKetThuc.is_(None),
        )
        .first()
    )
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Học viên không còn trong lớp này.",
        )
    effective_at = datetime.combine(request.ngay_hieu_luc, datetime.min.time())
    if effective_at < enrollment.NgayThamGia:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ngày hiệu lực không thể trước ngày học viên vào lớp.",
        )

    destination = None
    if request.loai_thao_tac == "ChuyenLop":
        destination = _get_class_or_404(db, request.lop_hoc_dich_id)
        if destination.LopHocId == class_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Lớp chuyển đến phải khác lớp hiện tại.",
            )
        if destination.TrangThai not in ACTIVE_CLASS_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lớp chuyển đến không còn nhận học viên.",
            )
        existing_destination = (
            db.query(LopHocHocVien)
            .filter(
                LopHocHocVien.LopHocId == destination.LopHocId,
                LopHocHocVien.HocVienId == student_id,
                LopHocHocVien.NgayThamGia <= effective_at,
                (LopHocHocVien.NgayKetThuc.is_(None))
                | (LopHocHocVien.NgayKetThuc > effective_at),
            )
            .first()
        )
        if existing_destination is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Học viên đã thuộc lớp chuyển đến vào ngày hiệu lực.",
            )
        destination_memberships = (
            db.query(LopHocHocVien)
            .filter(
                LopHocHocVien.LopHocId == destination.LopHocId,
                LopHocHocVien.NgayThamGia <= effective_at,
                (LopHocHocVien.NgayKetThuc.is_(None))
                | (LopHocHocVien.NgayKetThuc > effective_at),
            )
            .count()
        )
        destination_room = (
            db.query(PhongHoc)
            .filter(PhongHoc.PhongHocId == destination.PhongHocId)
            .first()
            if destination.PhongHocId is not None
            else None
        )
        capacity = min(
            destination.SiSoToiDa,
            destination_room.SucChua if destination_room else destination.SiSoToiDa,
        )
        if destination_memberships >= capacity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lớp chuyển đến đã đạt sĩ số tối đa hoặc sức chứa phòng.",
            )

    enrollment.NgayKetThuc = effective_at
    enrollment.TrangThaiGhiDanh = {
        "BaoLuu": "Bảo lưu",
        "ChuyenLop": "Chuyển lớp",
        "ThoiHoc": "Thôi học",
    }[request.loai_thao_tac]
    if destination is not None:
        db.add(
            LopHocHocVien(
                LopHocId=destination.LopHocId,
                HocVienId=student_id,
                NgayThamGia=effective_at,
                NguoiGhiDanhId=current_user.NguoiDungId,
                TrangThaiGhiDanh="Đang học",
            )
        )
    action = LopHocHocVienThaoTac(
        LopHocId=class_id,
        HocVienId=student_id,
        LoaiThaoTac=request.loai_thao_tac,
        NgayHieuLuc=effective_at,
        LopHocDichId=destination.LopHocId if destination else None,
        LyDo=request.ly_do,
        NguoiThucHienId=current_user.NguoiDungId,
        NgayTao=datetime.now(),
    )
    db.add(action)
    _commit(db, "Không thể lưu quyết định xử lý học viên.")
    return {
        "actionId": action.ThaoTacId,
        "loaiThaoTac": action.LoaiThaoTac,
        "ngayHieuLuc": action.NgayHieuLuc.date().isoformat(),
        "lopHocId": class_id,
        "lopHocDichId": action.LopHocDichId,
        "trangThai": enrollment.TrangThaiGhiDanh,
    }


@router.get(
    "/students/{student_id}/academic-profile",
    dependencies=[Depends(require_permission("GRADE_VIEW"))],
)
def get_student_academic_profile(
    student_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
            detail="Không tìm thấy hồ sơ học viên.",
        )
    roles = user_role_ids(db, current_user.NguoiDungId)
    is_admin = user_is_admin(db, current_user.NguoiDungId)
    if (
        current_user.NguoiDungId != student_id
        and not is_admin
        and not roles.intersection({7, *TEACHING_ROLE_IDS})
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem hồ sơ học viên này.",
        )
    if current_user.NguoiDungId == student_id:
        visible_classes = db.query(LopHoc).all()
    else:
        visible_classes = accessible_classes(
            db,
            current_user,
            include_inactive=True,
        )
    if current_user.NguoiDungId != student_id and not is_admin and 7 not in roles:
        visible_classes = [
            item for item in visible_classes
            if can_access_class(db, current_user, item)
        ]
    class_ids = {item.LopHocId for item in visible_classes}
    classes = (
        db.query(LopHoc)
        .join(
            LopHocHocVien,
            LopHocHocVien.LopHocId == LopHoc.LopHocId,
        )
        .filter(
            LopHocHocVien.HocVienId == student_id,
            LopHoc.LopHocId.in_(class_ids) if class_ids else False,
        )
        .order_by(LopHoc.NgayKhaiGiang.desc())
        .all()
    )
    grades = (
        db.query(Diem)
        .filter(
            Diem.HocVienId == student_id,
            Diem.LopHocId.in_([item.LopHocId for item in classes])
            if classes
            else False,
        )
        .order_by(Diem.NamHoc.desc(), Diem.HocKy, Diem.DiemId)
        .all()
    )
    conversion = (
        db.query(LeadConversion)
        .filter(LeadConversion.NguoiDungId == student_id)
        .first()
    )
    actions_query = db.query(LopHocHocVienThaoTac).filter(
        LopHocHocVienThaoTac.HocVienId == student_id,
        LopHocHocVienThaoTac.LopHocId.in_(class_ids) if class_ids else False,
    )
    actions = actions_query.order_by(
        LopHocHocVienThaoTac.NgayHieuLuc.desc(),
        LopHocHocVienThaoTac.ThaoTacId.desc(),
    ).all()
    action_class_ids = {
        class_id
        for action in actions
        for class_id in (action.LopHocId, action.LopHocDichId)
        if class_id is not None
    }
    action_classes = {
        item.LopHocId: item.MaLop
        for item in db.query(LopHoc)
        .filter(LopHoc.LopHocId.in_(action_class_ids))
        .all()
    } if action_class_ids else {}
    action_actor_ids = {item.NguoiThucHienId for item in actions}
    action_actors = {
        item.NguoiDungId: item.HoTen
        for item in db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId.in_(action_actor_ids))
        .all()
    } if action_actor_ids else {}
    class_history = []
    for item in classes:
        payload = _class_payload(db, item)
        payload["hocViens"] = [
            enrolled
            for enrolled in payload["hocViens"]
            if enrolled["nguoiDungId"] == student_id
        ]
        payload["hocVienIds"] = [student_id]
        payload["ngayGhiDanh"] = (
            db.query(LopHocHocVien.NgayThamGia)
            .filter(
                LopHocHocVien.LopHocId == item.LopHocId,
                LopHocHocVien.HocVienId == student_id,
            )
            .scalar()
        )
        class_history.append(payload)
    return {
        "hocVien": {
            "nguoiDungId": student.NguoiDungId,
            "hoTen": student.HoTen,
            "email": student.Email,
            "soDienThoai": student.SoDienThoai,
            "ngaySinh": student.NgaySinh,
            "diaChi": student.DiaChi,
            "trangThai": student.TrangThai,
            "trinhDoDauVao": student.TrinhDoDauVao,
            "ghiChu": student.GhiChuHoSo,
            "maHocVien": conversion.MaHocVien if conversion else None,
            "ngayNhapHoc": conversion.NgayNhapHoc if conversion else None,
        },
        "lopHocs": class_history,
        "thaoTacs": [
            {
                "actionId": item.ThaoTacId,
                "loaiThaoTac": item.LoaiThaoTac,
                "ngayHieuLuc": item.NgayHieuLuc.date().isoformat(),
                "lyDo": item.LyDo,
                "maLop": action_classes.get(item.LopHocId, ""),
                "maLopDich": action_classes.get(item.LopHocDichId),
                "nguoiThucHien": action_actors.get(item.NguoiThucHienId),
                "ngayTao": item.NgayTao.isoformat(),
            }
            for item in actions
        ],
        "diems": [_grade_payload(db, grade) for grade in grades],
    }


@router.put(
    "/students/{student_id}/academic-profile",
    dependencies=[Depends(require_permission("STUDENT_PROFILE_UPDATE"))],
)
def update_student_academic_profile(
    student_id: int,
    request: StudentProfileWrite,
    db: Session = Depends(get_db),
):
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
            detail="Không tìm thấy hồ sơ học viên.",
        )

    email = str(request.email).strip().lower()
    email_exists = (
        db.query(NguoiDung.NguoiDungId)
        .filter(
            NguoiDung.Email == email,
            NguoiDung.NguoiDungId != student_id,
        )
        .first()
    )
    if email_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email đã được sử dụng bởi tài khoản khác.",
        )

    student.HoTen = request.ho_ten
    student.Email = email
    student.SoDienThoai = request.so_dien_thoai
    student.NgaySinh = request.ngay_sinh
    student.DiaChi = request.dia_chi
    student.TrinhDoDauVao = request.trinh_do_dau_vao
    student.GhiChuHoSo = request.ghi_chu
    student.NgayCapNhat = datetime.now()
    _commit(db, "Không thể cập nhật hồ sơ học viên.")
    return {"message": "Đã cập nhật hồ sơ học viên."}


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
    room = (
        db.query(PhongHoc)
        .filter(PhongHoc.PhongHocId == lop_hoc.PhongHocId)
        .first()
        if lop_hoc.PhongHocId is not None
        else None
    )
    effective_capacity = min(
        lop_hoc.SiSoToiDa,
        room.SucChua if room is not None else lop_hoc.SiSoToiDa,
    )
    if len(current_ids) + len(new_ids) > effective_capacity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Số học viên vượt quá sĩ số tối đa của lớp hoặc sức chứa phòng.",
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
    dependencies=[Depends(require_permission("CURRICULUM_VIEW"))],
)
def list_subjects(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    query = db.query(MonHoc)
    if not include_inactive:
        query = query.filter(MonHoc.TrangThai == "Đang hoạt động")
    subjects = query.order_by(MonHoc.MaMonHoc).all()
    applied_subject_ids = {
        subject_id
        for (subject_id,) in db.query(ChuongTrinhMonHoc.MonHocId)
        .distinct()
        .all()
    }
    applied_subject_ids.update(
        subject_id
        for (subject_id,) in db.query(LopHocMonHoc.MonHocId).distinct().all()
    )
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
            "daApDung": subject.MonHocId in applied_subject_ids,
        }
        for subject in subjects
    ]


@router.post(
    "/subjects",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CURRICULUM_CREATE"))],
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
    return _subject_payload(subject)


@router.put(
    "/subjects/{subject_id}",
    dependencies=[Depends(require_permission("CURRICULUM_UPDATE"))],
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
    return _subject_payload(subject)


@router.post(
    "/subjects/{subject_id}/archive",
    dependencies=[Depends(require_permission("CURRICULUM_DELETE"))],
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
    if (
        db.query(LopHocMonHoc.MonHocId)
        .filter(LopHocMonHoc.MonHocId == subject_id)
        .first()
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Môn học đã có lớp học nên không thể xóa.",
        )
    subject.TrangThai = "Ngừng hoạt động"
    _commit(db, "Không thể lưu trữ môn học.")
    return {"message": "Đã lưu trữ môn học."}


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


@router.delete(
    "/subjects/{subject_id}",
    dependencies=[Depends(require_permission("CURRICULUM_DELETE"))],
)
def delete_subject(
    subject_id: int,
    db: Session = Depends(get_db),
):
    subject = db.query(MonHoc).filter(MonHoc.MonHocId == subject_id).first()
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy môn học.",
        )
    is_in_use = any(
        db.query(model).filter(model.MonHocId == subject_id).first() is not None
        for model in (LopHocMonHoc, ChuongTrinhMonHoc, Diem)
    )
    if is_in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Môn học đã được sử dụng trong lớp, chương trình hoặc bảng điểm nên không thể xóa.",
        )
    db.delete(subject)
    _commit(db, "Không thể xóa môn học đang được sử dụng.")
    return {"message": "Đã xóa môn học."}


def _subject_payload(subject: MonHoc) -> dict:
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


def _subject_option(subject: MonHoc) -> dict:
    """Dạng rút gọn của môn học cho danh sách lựa chọn/tùy chọn."""
    payload = _subject_payload(subject)
    return {
        "monHocId": payload["monHocId"],
        "maMonHoc": payload["maMonHoc"],
        "tenMonHoc": payload["tenMonHoc"],
    }


def _subject_option_with_credit(subject: MonHoc) -> dict:
    """Dạng rút gọn kèm số tín chỉ cho danh sách tùy chọn lớp."""
    payload = _subject_payload(subject)
    return {
        "monHocId": payload["monHocId"],
        "maMonHoc": payload["maMonHoc"],
        "tenMonHoc": payload["tenMonHoc"],
        "soTinChi": payload["soTinChi"],
    }


def _program_subject_row(
    db: Session,
    program_subject: ChuongTrinhMonHoc,
) -> dict:
    subject = db.query(MonHoc).filter(
        MonHoc.MonHocId == program_subject.MonHocId
    ).one()
    prerequisites = (
        db.query(ChuongTrinhMonHoc.MonHocId)
        .join(
            ChuongTrinhMonHocTienQuyet,
            ChuongTrinhMonHoc.ChuongTrinhMonHocId
            == ChuongTrinhMonHocTienQuyet.MonTienQuyetId,
        )
        .filter(
            ChuongTrinhMonHocTienQuyet.ChuongTrinhMonHocId
            == program_subject.ChuongTrinhMonHocId
        )
        .order_by(ChuongTrinhMonHoc.MonHocId)
        .all()
    )
    sessions = (
        db.query(BuoiHoc)
        .filter(BuoiHoc.ChuongTrinhMonHocId == program_subject.ChuongTrinhMonHocId)
        .order_by(BuoiHoc.SoThuTu)
        .all()
    )
    return {
        "monHocId": subject.MonHocId,
        "maMonHoc": subject.MaMonHoc,
        "tenMonHoc": subject.TenMonHoc,
        "soBuoi": subject.SoBuoi,
        "trongSo": float(subject.TrongSo),
        "moTaChuanDauRa": subject.MoTaChuanDauRa,
        "trangThai": subject.TrangThai,
        "thuTu": program_subject.ThuTu,
        "monTienQuyetId": prerequisites[0][0] if prerequisites else None,
        "sessions": [
            {
                "buoiHocId": session.BuoiHocId,
                "soThuTu": session.SoThuTu,
                "chuDe": session.ChuDe,
                "mucTieu": session.MucTieu,
            }
            for session in sessions
        ],
    }


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


def get_program_subjects_legacy(program_id: int, db: Session = Depends(get_db)):
    _get_program_or_404(db, program_id)
    associations = (
        db.query(ChuongTrinhMonHoc)
        .filter(ChuongTrinhMonHoc.ChuongTrinhId == program_id)
        .order_by(ChuongTrinhMonHoc.ThuTu)
        .all()
    )
    return [_program_subject_row(db, item) for item in associations]


@router.put(
    "/programs/{program_id}/subjects/replace",
    dependencies=[Depends(require_permission("CURRICULUM_UPDATE"))],
)
def replace_program_subjects(
    program_id: int,
    request: ProgramSubjectsWrite,
    db: Session = Depends(get_db),
):
    _get_program_or_404(db, program_id)
    rows_by_subject = {row.mon_hoc_id: row for row in request.subjects}
    requested_subject_ids = set(rows_by_subject)
    current_rows = (
        db.query(ChuongTrinhMonHoc)
        .filter(ChuongTrinhMonHoc.ChuongTrinhId == program_id)
        .all()
    )
    existing_subject_ids = {association.MonHocId for association in current_rows}
    subject_by_id = {
        subject.MonHocId: subject
        for subject in db.query(MonHoc)
        .filter(MonHoc.MonHocId.in_(requested_subject_ids))
        .all()
    } if requested_subject_ids else {}
    if len(subject_by_id) != len(requested_subject_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Có môn học không tồn tại.",
        )
    if any(
        subject.TrangThai != "Đang hoạt động"
        and subject_id not in existing_subject_ids
        for subject_id, subject in subject_by_id.items()
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Không thể thêm môn học đã ngừng hoạt động vào chương trình.",
        )
    for row in request.subjects:
        if row.mon_tien_quyet_id is not None:
            if row.mon_tien_quyet_id == row.mon_hoc_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Môn học không thể là tiên quyết của chính nó.",
                )
            if row.mon_tien_quyet_id not in requested_subject_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Môn tiên quyết phải thuộc cùng chương trình.",
                )

    try:
        prerequisite_by_subject = build_prerequisite_map(
            [
                (row.mon_hoc_id, row.mon_tien_quyet_id)
                for row in request.subjects
            ]
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    association_by_subject = {row.MonHocId: row for row in current_rows}
    removed = set(association_by_subject) - requested_subject_ids
    removed_ids = [
        association_by_subject[subject_id].ChuongTrinhMonHocId
        for subject_id in removed
    ]
    if removed_ids:
        db.query(ChuongTrinhMonHocTienQuyet).filter(
            (ChuongTrinhMonHocTienQuyet.ChuongTrinhMonHocId.in_(removed_ids))
            | (ChuongTrinhMonHocTienQuyet.MonTienQuyetId.in_(removed_ids))
        ).delete(synchronize_session=False)
        db.query(BuoiHoc).filter(
            BuoiHoc.ChuongTrinhMonHocId.in_(removed_ids)
        ).delete(synchronize_session=False)
        db.query(ChuongTrinhMonHoc).filter(
            ChuongTrinhMonHoc.ChuongTrinhMonHocId.in_(removed_ids)
        ).delete(synchronize_session=False)

    # Shift existing sequence values above the current range before reordering;
    # keep the database's positive-sequence check valid during the transaction.
    highest_sequence = max(
        (association.ThuTu for association in association_by_subject.values()),
        default=0,
    )
    sequence_offset = highest_sequence + len(association_by_subject) + len(request.subjects) + 1
    for association in association_by_subject.values():
        if association.MonHocId in requested_subject_ids:
            association.ThuTu += sequence_offset
    db.flush()
    for item in request.subjects:
        association = association_by_subject.get(item.mon_hoc_id)
        if association is None:
            association = ChuongTrinhMonHoc(
                ChuongTrinhId=program_id,
                MonHocId=item.mon_hoc_id,
                ThuTu=item.thu_tu,
            )
            db.add(association)
            db.flush()
            association_by_subject[item.mon_hoc_id] = association
        association.ThuTu = item.thu_tu

    assoc_ids = [
        association_by_subject[subject_id].ChuongTrinhMonHocId
        for subject_id in requested_subject_ids
    ]
    if assoc_ids:
        db.query(ChuongTrinhMonHocTienQuyet).filter(
            ChuongTrinhMonHocTienQuyet.ChuongTrinhMonHocId.in_(assoc_ids)
        ).delete(synchronize_session=False)
    for subject_id, prerequisite_id in prerequisite_by_subject.items():
        db.add(
            ChuongTrinhMonHocTienQuyet(
                ChuongTrinhMonHocId=association_by_subject[
                    subject_id
                ].ChuongTrinhMonHocId,
                MonTienQuyetId=association_by_subject[
                    prerequisite_id
                ].ChuongTrinhMonHocId,
            )
        )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể lưu thứ tự hoặc môn học của chương trình.",
        ) from error
    return get_program_subjects(program_id, db)


def _program_subject_or_404(
    db: Session,
    program_id: int,
    subject_id: int,
) -> ChuongTrinhMonHoc:
    association = (
        db.query(ChuongTrinhMonHoc)
        .filter(
            ChuongTrinhMonHoc.ChuongTrinhId == program_id,
            ChuongTrinhMonHoc.MonHocId == subject_id,
        )
        .first()
    )
    if association is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Môn học chưa được gắn với chương trình này.",
        )
    return association


@router.get(
    "/programs/{program_id}/subjects/{subject_id}/sessions",
    dependencies=[Depends(require_permission("CURRICULUM_VIEW"))],
)
def get_program_subject_sessions(
    program_id: int,
    subject_id: int,
    db: Session = Depends(get_db),
):
    _get_program_or_404(db, program_id)
    association = _program_subject_or_404(db, program_id, subject_id)
    return _program_subject_row(db, association)


@router.put(
    "/programs/{program_id}/subjects/{subject_id}/sessions/replace",
    dependencies=[Depends(require_permission("CURRICULUM_UPDATE"))],
)
def replace_program_subject_sessions(
    program_id: int,
    subject_id: int,
    request: SessionsWrite,
    db: Session = Depends(get_db),
):
    _get_program_or_404(db, program_id)
    association = _program_subject_or_404(db, program_id, subject_id)
    subject = db.query(MonHoc).filter(MonHoc.MonHocId == subject_id).one()
    if len(request.sessions) > subject.SoBuoi:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Môn học chỉ được có tối đa {subject.SoBuoi} buổi.",
        )
    db.query(BuoiHoc).filter(
        BuoiHoc.ChuongTrinhMonHocId == association.ChuongTrinhMonHocId
    ).delete(synchronize_session=False)
    db.add_all(
        [
            BuoiHoc(
                ChuongTrinhMonHocId=association.ChuongTrinhMonHocId,
                SoThuTu=item.so_thu_tu,
                ChuDe=item.chu_de,
                MucTieu=item.muc_tieu,
            )
            for item in request.sessions
        ]
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể lưu danh sách buổi học.",
        ) from error
    return _program_subject_row(db, association)


@router.post(
    "/programs/{program_id}/subjects/{subject_id}/sessions/clone-legacy",
    dependencies=[Depends(require_permission("CURRICULUM_UPDATE"))],
)
def clone_program_subject_sessions(
    program_id: int,
    subject_id: int,
    request: SessionCloneWrite,
    db: Session = Depends(get_db),
):
    _get_program_or_404(db, program_id)
    target_association = _program_subject_or_404(db, program_id, subject_id)
    target_subject = db.query(MonHoc).filter(MonHoc.MonHocId == subject_id).one()

    source_assoc = None
    if request.source_program_id is not None:
        source_assoc = (
            db.query(ChuongTrinhMonHoc)
            .filter(
                ChuongTrinhMonHoc.ChuongTrinhId == request.source_program_id,
                ChuongTrinhMonHoc.MonHocId == request.source_subject_id,
            )
            .first()
        )
    else:
        source_assoc = (
            db.query(ChuongTrinhMonHoc)
            .filter(
                ChuongTrinhMonHoc.ChuongTrinhId == program_id,
                ChuongTrinhMonHoc.MonHocId == request.source_subject_id,
            )
            .first()
        )
        if source_assoc is None:
            source_assoc = (
                db.query(ChuongTrinhMonHoc)
                .join(
                    BuoiHoc,
                    BuoiHoc.ChuongTrinhMonHocId == ChuongTrinhMonHoc.ChuongTrinhMonHocId,
                )
                .filter(ChuongTrinhMonHoc.MonHocId == request.source_subject_id)
                .first()
            )

    if source_assoc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy môn học nguồn hoặc môn học nguồn chưa được cấu hình buổi học.",
        )

    source_sessions = (
        db.query(BuoiHoc)
        .filter(BuoiHoc.ChuongTrinhMonHocId == source_assoc.ChuongTrinhMonHocId)
        .order_by(BuoiHoc.SoThuTu)
        .all()
    )

    if not source_sessions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Môn học nguồn chưa có danh sách buổi học để nhân bản.",
        )

    cloned_sessions = source_sessions[: target_subject.SoBuoi]

    db.query(BuoiHoc).filter(
        BuoiHoc.ChuongTrinhMonHocId == target_association.ChuongTrinhMonHocId
    ).delete(synchronize_session=False)

    db.add_all(
        [
            BuoiHoc(
                ChuongTrinhMonHocId=target_association.ChuongTrinhMonHocId,
                SoThuTu=index + 1,
                ChuDe=item.ChuDe,
                MucTieu=item.MucTieu,
            )
            for index, item in enumerate(cloned_sessions)
        ]
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể nhân bản danh sách buổi học.",
        ) from error

    return _program_subject_row(db, target_association)
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
                    _subject_option(subject)
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
