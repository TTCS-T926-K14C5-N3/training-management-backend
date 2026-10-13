from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.diem import Diem
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.mon_hoc import MonHoc
from app.models.program_subject import (
    BuoiHoc,
    ChuongTrinhMonHoc,
    ChuongTrinhMonHocTienQuyet,
)
from app.schemas.academic import (
    ClassWrite,
    GradeWrite,
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
    STUDENT_ROLE_ID,
    accessible_classes,
    accessible_grades_query,
    build_prerequisite_map,
    can_access_class,
    ensure_active_instructor,
    ensure_active_student,
    ensure_active_subjects,
    ensure_valid_academic_year,
    user_role_ids,
)


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
            _subject_option(subject)
            for subject in subjects
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

    lop_hoc.MaLop = request.ma_lop.strip()
    lop_hoc.TenLop = request.ten_lop.strip()
    lop_hoc.NamHoc = request.nam_hoc
    lop_hoc.ChuongTrinhId = request.chuong_trinh_id
    lop_hoc.GiangVienId = request.giang_vien_id

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
    if lop_hoc.TrangThai != "Đang hoạt động":
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
            NguoiDungVaiTro.VaiTroId == INSTRUCTOR_ROLE_ID,
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
    return {
        "giangViens": [
            {
                "nguoiDungId": user.NguoiDungId,
                "hoTen": user.HoTen,
                "email": user.Email,
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
    if lop_hoc.TrangThai != "Đang hoạt động":
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


@router.delete(
    "/subjects/{subject_id}",
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
    subject_by_id = {
        subject.MonHocId: subject
        for subject in db.query(MonHoc)
        .filter(
            MonHoc.MonHocId.in_(requested_subject_ids),
            MonHoc.TrangThai == "Đang hoạt động",
        )
        .all()
    } if requested_subject_ids else {}
    if len(subject_by_id) != len(requested_subject_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Môn học không tồn tại hoặc đã lưu trữ.",
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

    current_rows = (
        db.query(ChuongTrinhMonHoc)
        .filter(ChuongTrinhMonHoc.ChuongTrinhId == program_id)
        .all()
    )
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
