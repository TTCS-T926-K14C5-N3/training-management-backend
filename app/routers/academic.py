from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.diem import Diem
from app.models.admissions import LeadConversion
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.student_enrollment_action import StudentEnrollmentAction
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
from app.schemas.academic import (
    ClassEnrollmentWrite,
    ClassWrite,
    GradeWrite,
    RoomWrite,
    StudentEnrollmentActionWrite,
    StudentProfileWrite,
    SubjectCreate,
    SubjectUpdate,
    TrainingProgramWrite,
)
from app.schemas.curriculum import (
    ProgramSubjectsWrite,
    SessionCloneWrite,
    SessionsWrite,
)
from app.services.academic_service import (
    INSTRUCTOR_ROLE_ID,
    ASSISTANT_ROLE_ID,
    TRAINING_MANAGER_ROLE_ID,
    TEACHING_ROLE_IDS,
    STUDENT_ROLE_ID,
    accessible_classes,
    accessible_grades_query,
    build_prerequisite_map,
    can_access_class,
    ensure_active_instructor,
    ensure_active_student,
    ensure_active_subjects,
    ensure_valid_academic_year,
    user_is_admin,
    user_role_ids,
)


router = APIRouter(prefix="/academic", tags=["Academic management"])
CLASS_STATUS_TRANSITIONS = {
    "Chuẩn bị": {"Đang học", "Hủy"},
    "Đang học": {"Kết thúc", "Hủy"},
    "Đang hoạt động": {"Đang học", "Kết thúc", "Hủy"},
    "Kết thúc": set(),
    "Hủy": set(),
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
    today = date.today()
    ended_enrollment_ids = {
        row.HocVienId
        for row in db.query(StudentEnrollmentAction.HocVienId)
        .filter(
            StudentEnrollmentAction.LopHocId == lop_hoc.LopHocId,
            StudentEnrollmentAction.NgayHieuLuc <= today,
        )
        .distinct()
        .all()
    }
    students = (
        db.query(NguoiDung)
        .join(
            LopHocHocVien,
            LopHocHocVien.HocVienId == NguoiDung.NguoiDungId,
        )
        .filter(
            LopHocHocVien.LopHocId == lop_hoc.LopHocId,
            LopHocHocVien.NgayThamGia < datetime.combine(
                today, datetime.max.time()
            ),
            ~LopHocHocVien.HocVienId.in_(ended_enrollment_ids)
            if ended_enrollment_ids
            else True,
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
        .filter(LopHocHocVien.LopHocId == lop_hoc.LopHocId)
        .all()
    )
    enrollment_by_student = {
        row.HocVienId: row for row in enrollment_rows
    }
    pending_actions = (
        db.query(StudentEnrollmentAction)
        .filter(
            StudentEnrollmentAction.LopHocId == lop_hoc.LopHocId,
            StudentEnrollmentAction.NgayHieuLuc > today,
        )
        .order_by(StudentEnrollmentAction.NgayHieuLuc)
        .all()
    )
    pending_action_by_student = {
        action.HocVienId: action for action in pending_actions
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
        .all()
    )
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
        "ngayKhaiGiang": lop_hoc.NgayKhaiGiang,
        "siSoHienTai": len(students),
        "siSoToiDa": lop_hoc.SiSoToiDa,
        "canhBaoSiSo": len(students) > lop_hoc.SiSoToiDa,
        "hinhThuc": lop_hoc.HinhThuc,
        "phongHocId": lop_hoc.PhongHocId,
        "maPhong": room.MaPhong if room else None,
        "tenPhong": room.TenPhong if room else None,
        "sucChuaPhong": room.SucChua if room else None,
        "canhBaoSucChuaPhong": (
            room is not None and len(students) > room.SucChua
        ),
        "linkTrucTuyen": lop_hoc.LinkTrucTuyen,
        "tienDo": float(lop_hoc.TienDo or 0),
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
                "trangThaiGhiDanh": (
                    {
                        "BaoLuu": "Sắp bảo lưu",
                        "ChuyenLop": "Sắp chuyển lớp",
                        "ThoiHoc": "Sắp thôi học",
                    }[pending_action_by_student[student.NguoiDungId].LoaiThaoTac]
                    if student.NguoiDungId in pending_action_by_student
                    else "Đang học"
                ),
                "ngayHieuLuc": (
                    pending_action_by_student[student.NguoiDungId].NgayHieuLuc
                    if student.NguoiDungId in pending_action_by_student
                    else None
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
        "phanCongGiangVien": [
            {
                "monHocId": assignment.MonHocId,
                "giangVienId": assignment.GiangVienId,
                "vaiTro": assignment.VaiTro,
            }
            for assignment in teaching_rows
        ],
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
    if request.hinh_thuc == "Trực tuyến" and not request.link_truc_tuyen:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Lớp trực tuyến cần có liên kết học trực tuyến.",
        )

    try:
        if request.giang_vien_id is not None:
            ensure_active_instructor(db, request.giang_vien_id)
        for student_id in sorted(student_ids):
            ensure_active_student(db, student_id)
        ensure_active_subjects(db, request.mon_hoc_ids)
        for assignment in request.phan_cong_giang_vien:
            ensure_active_instructor(db, assignment.giang_vien_id)
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
    currently_enrolled_students = {
        item["nguoiDungId"] for item in _class_payload(db, lop_hoc)["hocViens"]
    }
    removed_students = currently_enrolled_students - student_ids
    if removed_students:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Không thể xóa học viên khỏi lịch sử lớp. "
                "Hãy dùng thao tác bảo lưu, chuyển lớp hoặc thôi học."
            ),
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
        for item in request.phan_cong_giang_vien
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
    for subject_id in {subject_id for subject_id, _, _ in requested_assignments}:
        subject_assignments = [
            role for assigned_subject, _, role in requested_assignments
            if assigned_subject == subject_id
        ]
        if subject_assignments.count("Chính") != 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Mỗi môn có phân công cần đúng một giảng viên chính.",
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
    if lop_hoc.TrangThai not in {"Chuẩn bị", "Đang học", "Đang hoạt động"}:
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


@router.get(
    "/rooms",
    dependencies=[Depends(require_permission("CLASS_VIEW"))],
)
def list_rooms(db: Session = Depends(get_db)):
    return [
        {
            "phongHocId": room.PhongHocId,
            "maPhong": room.MaPhong,
            "tenPhong": room.TenPhong,
            "sucChua": room.SucChua,
            "trangThai": room.TrangThai,
        }
        for room in db.query(PhongHoc).order_by(PhongHoc.MaPhong).all()
    ]


@router.post(
    "/rooms",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CLASS_CREATE"))],
)
def create_room(request: RoomWrite, db: Session = Depends(get_db)):
    room = PhongHoc(
        MaPhong=request.ma_phong,
        TenPhong=request.ten_phong,
        SucChua=request.suc_chua,
        TrangThai="Đang hoạt động",
    )
    db.add(room)
    _commit(db, "Mã phòng đã tồn tại hoặc thông tin phòng không hợp lệ.")
    return {
        "phongHocId": room.PhongHocId,
        "maPhong": room.MaPhong,
        "tenPhong": room.TenPhong,
        "sucChua": room.SucChua,
        "trangThai": room.TrangThai,
    }


@router.post(
    "/classes/{class_id}/students/{student_id}/actions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("CLASS_UPDATE"))],
)
def create_student_enrollment_action(
    class_id: int,
    student_id: int,
    request: StudentEnrollmentActionWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    class_record = _get_class_or_404(db, class_id)
    _ensure_class_scope(db, current_user, class_record)
    enrollment = (
        db.query(LopHocHocVien)
        .filter(
            LopHocHocVien.LopHocId == class_id,
            LopHocHocVien.HocVienId == student_id,
        )
        .first()
    )
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy học viên trong lịch sử lớp này.",
        )
    if request.ngay_hieu_luc < enrollment.NgayThamGia.date():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ngày hiệu lực không được trước ngày ghi danh.",
        )
    target_class = None
    if request.loai_thao_tac == "ChuyenLop":
        if request.lop_hoc_dich_id is None or request.lop_hoc_dich_id == class_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Vui lòng chọn lớp chuyển đến khác lớp hiện tại.",
            )
        target_class = _get_class_or_404(db, request.lop_hoc_dich_id)
        _ensure_class_scope(db, current_user, target_class)
        if target_class.TrangThai not in {"Chuẩn bị", "Đang học", "Đang hoạt động"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Không thể chuyển học viên vào lớp đã kết thúc hoặc hủy.",
            )
        existing_target = (
            db.query(LopHocHocVien)
            .filter(
                LopHocHocVien.LopHocId == target_class.LopHocId,
                LopHocHocVien.HocVienId == student_id,
            )
            .first()
        )
        if existing_target is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Học viên đã có lịch sử ghi danh trong lớp đích.",
            )
        if len(_class_payload(db, target_class)["hocVienIds"]) >= target_class.SiSoToiDa:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lớp chuyển đến đã đủ sĩ số.",
            )
    elif request.lop_hoc_dich_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Chỉ thao tác chuyển lớp được chọn lớp đích.",
        )

    duplicate_action = (
        db.query(StudentEnrollmentAction.ActionId)
        .filter(
            StudentEnrollmentAction.LopHocId == class_id,
            StudentEnrollmentAction.HocVienId == student_id,
        )
        .first()
    )
    if duplicate_action is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Đã có thao tác hiệu lực từ ngày này trở đi cho học viên.",
        )

    action = StudentEnrollmentAction(
        HocVienId=student_id,
        LopHocId=class_id,
        LopHocDichId=request.lop_hoc_dich_id,
        LoaiThaoTac=request.loai_thao_tac,
        NgayHieuLuc=request.ngay_hieu_luc,
        LyDo=request.ly_do,
        NguoiThucHienId=current_user.NguoiDungId,
        NgayTao=datetime.now(),
    )
    db.add(action)
    if target_class is not None:
        db.add(
            LopHocHocVien(
                LopHocId=target_class.LopHocId,
                HocVienId=student_id,
                NgayThamGia=datetime.combine(
                    request.ngay_hieu_luc, datetime.min.time()
                ),
                NguoiGhiDanhId=current_user.NguoiDungId,
            )
        )
    _commit(db, "Không thể lưu thao tác học viên.")
    return {
        "actionId": action.ActionId,
        "hocVienId": action.HocVienId,
        "lopHocId": action.LopHocId,
        "lopHocDichId": action.LopHocDichId,
        "loaiThaoTac": action.LoaiThaoTac,
        "ngayHieuLuc": action.NgayHieuLuc,
        "lyDo": action.LyDo,
        "nguoiThucHienId": action.NguoiThucHienId,
    }


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
    _commit(db, "Mã phòng đã tồn tại hoặc thông tin phòng không hợp lệ.")
    return {
        "phongHocId": room.PhongHocId,
        "maPhong": room.MaPhong,
        "tenPhong": room.TenPhong,
        "sucChua": room.SucChua,
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
            {
                "phongHocId": room.PhongHocId,
                "maPhong": room.MaPhong,
                "tenPhong": room.TenPhong,
                "sucChua": room.SucChua,
            }
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
    "/classes/{class_id}/enrollments",
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
    historical_ids = {
        row.HocVienId
        for row in db.query(LopHocHocVien.HocVienId)
        .filter(LopHocHocVien.LopHocId == lop_hoc.LopHocId)
        .all()
    }
    already_enrolled_ids = historical_ids.intersection(request.hoc_vien_ids)
    if already_enrolled_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Một hoặc nhiều học viên đã được ghi danh trong lớp. "
                "Tải lại danh sách và chọn học viên khác."
            ),
        )
    new_ids = set(request.hoc_vien_ids) - historical_ids
    active_ids = set(_class_payload(db, lop_hoc)["hocVienIds"])
    if len(active_ids) + len(new_ids) > lop_hoc.SiSoToiDa:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Số học viên vượt quá sĩ số tối đa của lớp.",
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
        "daCoTrongLop": sorted(historical_ids & set(request.hoc_vien_ids)),
        "siSoHienTai": len(active_ids) + len(new_ids),
        "siSoToiDa": lop_hoc.SiSoToiDa,
    }


@router.get(
    "/students/statuses",
    dependencies=[Depends(require_permission("GRADE_VIEW"))],
)
def list_student_enrollment_statuses(
    search: str | None = Query(default=None, max_length=150),
    class_id: int | None = Query(default=None, alias="classId", gt=0),
    enrollment_status: str | None = Query(
        default=None,
        alias="enrollmentStatus",
        max_length=30,
    ),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed_statuses = {
        "Đang học",
        "Sắp bảo lưu",
        "Sắp chuyển lớp",
        "Sắp thôi học",
        "Bảo lưu",
        "Thôi học",
        "Đã chuyển lớp",
        "Đã kết thúc",
        "Chưa ghi danh",
    }
    if enrollment_status and enrollment_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Trạng thái ghi danh không hợp lệ.",
        )

    roles = user_role_ids(db, current_user.NguoiDungId)
    is_admin = user_is_admin(db, current_user.NguoiDungId)
    visible_classes = accessible_classes(db, current_user, include_inactive=True)
    visible_class_ids = {item.LopHocId for item in visible_classes}
    student_query = (
        db.query(NguoiDung)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(NguoiDungVaiTro.VaiTroId == STUDENT_ROLE_ID)
    )
    if is_admin or TRAINING_MANAGER_ROLE_ID in roles:
        pass
    elif roles.intersection(TEACHING_ROLE_IDS):
        student_query = student_query.filter(
            NguoiDung.NguoiDungId.in_(
                db.query(LopHocHocVien.HocVienId).filter(
                    LopHocHocVien.LopHocId.in_(visible_class_ids)
                    if visible_class_ids
                    else False
                )
            )
        )
    elif STUDENT_ROLE_ID in roles:
        student_query = student_query.filter(
            NguoiDung.NguoiDungId == current_user.NguoiDungId
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem tình trạng học viên.",
        )

    if class_id is not None:
        if class_id not in visible_class_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không được truy cập lớp học này.",
            )
        student_query = student_query.filter(
            NguoiDung.NguoiDungId.in_(
                db.query(LopHocHocVien.HocVienId).filter(
                    LopHocHocVien.LopHocId == class_id
                )
            )
        )

    normalized_search = (search or "").strip()
    if normalized_search:
        search_pattern = f"%{normalized_search}%"
        class_student_ids = (
            db.query(LopHocHocVien.HocVienId)
            .join(LopHoc, LopHoc.LopHocId == LopHocHocVien.LopHocId)
            .filter(
                LopHoc.LopHocId.in_(visible_class_ids)
                if visible_class_ids
                else False,
                (LopHoc.MaLop.ilike(search_pattern))
                | (LopHoc.TenLop.ilike(search_pattern)),
            )
        )
        student_query = student_query.filter(
            NguoiDung.NguoiDungId.in_(
                db.query(LeadConversion.NguoiDungId).filter(
                    LeadConversion.MaHocVien.ilike(search_pattern)
                )
            )
            | NguoiDung.HoTen.ilike(search_pattern)
            | NguoiDung.NguoiDungId.in_(class_student_ids)
        )

    students = student_query.distinct().order_by(NguoiDung.HoTen).all()
    student_ids = [item.NguoiDungId for item in students]
    class_ids = visible_class_ids
    enrollment_rows = (
        db.query(LopHocHocVien, LopHoc)
        .join(LopHoc, LopHoc.LopHocId == LopHocHocVien.LopHocId)
        .filter(
            LopHocHocVien.HocVienId.in_(student_ids) if student_ids else False,
            LopHoc.LopHocId.in_(class_ids) if class_ids else False,
        )
        .all()
    )
    enrollments_by_student: dict[int, list[tuple[LopHocHocVien, LopHoc]]] = {}
    for enrollment, class_record in enrollment_rows:
        enrollments_by_student.setdefault(enrollment.HocVienId, []).append(
            (enrollment, class_record)
        )
    action_rows = (
        db.query(StudentEnrollmentAction)
        .filter(
            StudentEnrollmentAction.HocVienId.in_(student_ids)
            if student_ids
            else False,
            StudentEnrollmentAction.LopHocId.in_(class_ids)
            if class_ids
            else False,
        )
        .order_by(
            StudentEnrollmentAction.NgayHieuLuc.desc(),
            StudentEnrollmentAction.ActionId.desc(),
        )
        .all()
    )
    actions_by_student: dict[int, list[StudentEnrollmentAction]] = {}
    for action in action_rows:
        actions_by_student.setdefault(action.HocVienId, []).append(action)
    conversions = {
        conversion.NguoiDungId: conversion.MaHocVien
        for conversion in db.query(LeadConversion)
        .filter(LeadConversion.NguoiDungId.in_(student_ids))
        .all()
    } if student_ids else {}

    today = date.today()
    status_labels = {
        "BaoLuu": ("Sắp bảo lưu", "Bảo lưu"),
        "ChuyenLop": ("Sắp chuyển lớp", "Đã chuyển lớp"),
        "ThoiHoc": ("Sắp thôi học", "Thôi học"),
    }
    records = []
    for student in students:
        enrollments = enrollments_by_student.get(student.NguoiDungId, [])
        actions = actions_by_student.get(student.NguoiDungId, [])
        ended_class_ids = {
            action.LopHocId
            for action in actions
            if action.NgayHieuLuc <= today
        }
        current_classes = [
            class_record
            for enrollment, class_record in enrollments
            if enrollment.NgayThamGia.date() <= today
            and class_record.TrangThai
            in {"Chuẩn bị", "Đang học", "Đang hoạt động"}
            and class_record.LopHocId not in ended_class_ids
        ]
        pending_actions = [
            action for action in actions if action.NgayHieuLuc > today
        ]
        effective_actions = [
            action for action in actions if action.NgayHieuLuc <= today
        ]
        if current_classes and pending_actions:
            latest_action = min(
                pending_actions,
                key=lambda item: (item.NgayHieuLuc, item.ActionId),
            )
            status_label = status_labels[latest_action.LoaiThaoTac][0]
            effective_date = latest_action.NgayHieuLuc
        elif current_classes:
            status_label = "Đang học"
            effective_date = None
        elif effective_actions:
            latest_action = max(
                effective_actions,
                key=lambda item: (item.NgayHieuLuc, item.ActionId),
            )
            status_label = status_labels[latest_action.LoaiThaoTac][1]
            effective_date = latest_action.NgayHieuLuc
        elif enrollments:
            status_label = "Đã kết thúc"
            effective_date = None
        else:
            status_label = "Chưa ghi danh"
            effective_date = None

        all_classes = [class_record for _, class_record in enrollments]
        if class_id is not None and not any(
            item.LopHocId == class_id for item in all_classes
        ):
            continue
        if enrollment_status and status_label != enrollment_status:
            continue
        records.append(
            {
                "nguoiDungId": student.NguoiDungId,
                "maHocVien": conversions.get(student.NguoiDungId),
                "hoTen": student.HoTen,
                "email": student.Email,
                "soDienThoai": student.SoDienThoai,
                "vaiTroId": STUDENT_ROLE_ID,
                "vaiTroIds": [STUDENT_ROLE_ID],
                "trangThaiTaiKhoan": student.TrangThai,
                "trangThaiGhiDanh": status_label,
                "ngayHieuLuc": effective_date,
                "lopHienTai": [
                    {
                        "lopHocId": item.LopHocId,
                        "maLop": item.MaLop,
                        "tenLop": item.TenLop,
                    }
                    for item in current_classes
                ],
                "lopHocs": [
                    {
                        "lopHocId": item.LopHocId,
                        "maLop": item.MaLop,
                        "tenLop": item.TenLop,
                        "trangThai": item.TrangThai,
                    }
                    for item in all_classes
                ],
            }
        )

    total = len(records)
    offset = (page - 1) * limit
    return {
        "items": records[offset : offset + limit],
        "classes": [
            {
                "lopHocId": item.LopHocId,
                "maLop": item.MaLop,
                "tenLop": item.TenLop,
                "trangThai": item.TrangThai,
            }
            for item in visible_classes
        ],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (total + limit - 1) // limit,
        },
    }


@router.get(
    "/students/{student_id}",
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
    visible_classes = accessible_classes(
        db,
        current_user,
        include_inactive=True,
    )
    if (
        current_user.NguoiDungId != student_id
        and not is_admin
        and 7 not in roles
    ):
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
    action_rows = (
        db.query(StudentEnrollmentAction)
        .filter(
            StudentEnrollmentAction.HocVienId == student_id,
            StudentEnrollmentAction.LopHocId.in_(class_ids)
            if class_ids
            else False,
        )
        .order_by(
            StudentEnrollmentAction.NgayHieuLuc.desc(),
            StudentEnrollmentAction.ActionId.desc(),
        )
        .all()
    )
    referenced_class_ids = {
        referenced_id
        for action in action_rows
        for referenced_id in (action.LopHocId, action.LopHocDichId)
        if referenced_id is not None
    }
    action_classes = (
        {
            item.LopHocId: item
            for item in db.query(LopHoc)
            .filter(LopHoc.LopHocId.in_(referenced_class_ids))
            .all()
        }
        if referenced_class_ids
        else {}
    )
    actor_ids = {item.NguoiThucHienId for item in action_rows}
    action_actors = (
        {
            item.NguoiDungId: item.HoTen
            for item in db.query(NguoiDung)
            .filter(NguoiDung.NguoiDungId.in_(actor_ids))
            .all()
        }
        if actor_ids
        else {}
    )
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
                "actionId": item.ActionId,
                "loaiThaoTac": item.LoaiThaoTac,
                "ngayHieuLuc": item.NgayHieuLuc,
                "lyDo": item.LyDo,
                "lopHocId": item.LopHocId,
                "maLop": action_classes[item.LopHocId].MaLop,
                "lopHocDichId": item.LopHocDichId,
                "maLopDich": (
                    action_classes[item.LopHocDichId].MaLop
                    if item.LopHocDichId in action_classes
                    else None
                ),
                "nguoiThucHien": action_actors.get(item.NguoiThucHienId),
                "ngayTao": item.NgayTao,
            }
            for item in action_rows
        ],
        "diems": [_grade_payload(db, grade) for grade in grades],
    }


@router.put(
    "/students/{student_id}",
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
    dependencies=[Depends(require_permission("CURRICULUM_DELETE"))],
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


def _get_program_or_404(db: Session, program_id: int) -> ChuongTrinhDaoTao:
    program = db.query(ChuongTrinhDaoTao).filter(
        ChuongTrinhDaoTao.ChuongTrinhId == program_id
    ).first()
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy chương trình đào tạo.",
        )
    return program


@router.get(
    "/programs/{program_id}/subjects",
    dependencies=[Depends(require_permission("CURRICULUM_VIEW"))],
)
def get_program_subjects(program_id: int, db: Session = Depends(get_db)):
    _get_program_or_404(db, program_id)
    associations = (
        db.query(ChuongTrinhMonHoc)
        .filter(ChuongTrinhMonHoc.ChuongTrinhId == program_id)
        .order_by(ChuongTrinhMonHoc.ThuTu)
        .all()
    )
    return [_program_subject_row(db, item) for item in associations]


@router.put(
    "/programs/{program_id}/subjects",
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
    "/programs/{program_id}/subjects/{subject_id}/sessions",
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
    "/programs/{program_id}/subjects/{subject_id}/sessions/clone",
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
        active_student_ids = set(_class_payload(db, lop_hoc)["hocVienIds"])
        student_query = student_query.filter(
            NguoiDung.NguoiDungId.in_(active_student_ids)
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
