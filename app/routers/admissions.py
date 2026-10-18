import hashlib
import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import FRONTEND_URL
from app.core.security import get_current_user
from app.database import get_db
from app.models.admissions import (
    AdmissionsLead,
    AdmissionsLeadAssignment,
    AdmissionsLeadInteraction,
    AdmissionsLeadStatusHistory,
)
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.quyen import Quyen
from app.models.student_enrollment_action import StudentEnrollmentAction
from app.models.tuyen_sinh_lead_chuyen_doi import TuyenSinhLeadChuyenDoi
from app.models.token_kich_hoat import TokenKichHoat
from app.models.vai_tro import VaiTro
from app.models.vai_tro_quyen import VaiTroQuyen
from app.schemas.admissions import (
    LeadAssignmentWrite,
    LeadBulkAssignmentWrite,
    LeadInteractionWrite,
    LeadStatusWrite,
    LeadWrite,
    PublicLeadWrite,
)
from app.services.auth_service import password_hash
from app.services.business_time import business_now, business_now_naive
from app.services.email_service import send_activation_email


router = APIRouter(prefix="/admissions", tags=["Admissions"])
TRAINING_MANAGER_ROLE_ID = 7
ADMIN_ROLE_ID = 8
ADMISSIONS_ROLE_ID = 5
TERMINAL_STATUSES = {"Đã nhập học", "Từ chối", "Đã chuyển đổi", "Không tiềm năng"}
VALID_STATUSES = {
    "Mới",
    "Đã liên hệ",
    "Đang tư vấn",
    "Hẹn học thử",
    "Chốt",
    "Từ chối",
    "Đang liên hệ",
    "Tiềm năng",
    "Đã chuyển đổi",
    "Đã nhập học",
    "Không tiềm năng",
}
STATUS_TRANSITIONS = {
    "Mới": {"Đã liên hệ", "Đang tư vấn", "Hẹn học thử", "Từ chối"},
    "Đã liên hệ": {"Đang tư vấn", "Hẹn học thử", "Từ chối"},
    "Đang tư vấn": {"Hẹn học thử", "Chốt", "Từ chối"},
    "Hẹn học thử": {"Chốt", "Từ chối"},
    "Đang liên hệ": {"Đang tư vấn", "Hẹn học thử", "Chốt", "Từ chối"},
    "Tiềm năng": {"Hẹn học thử", "Chốt", "Từ chối"},
}


def _role_ids(db: Session, user_id: int) -> set[int]:
    return {
        role_id
        for (role_id,) in db.query(NguoiDungVaiTro.VaiTroId)
        .filter(NguoiDungVaiTro.NguoiDungId == user_id)
        .all()
    }


def _active_assignment_filter():
    return AdmissionsLeadAssignment.DangPhanCong == true()


def _has_permission(db: Session, user_id: int, code: str) -> bool:
    return (
        db.query(Quyen.QuyenId)
        .join(VaiTroQuyen, VaiTroQuyen.QuyenId == Quyen.QuyenId)
        .join(NguoiDungVaiTro, NguoiDungVaiTro.VaiTroId == VaiTroQuyen.VaiTroId)
        .filter(
            NguoiDungVaiTro.NguoiDungId == user_id,
            Quyen.MaQuyen == code,
        )
        .first()
        is not None
    )


def _is_manager(db: Session, user: NguoiDung) -> bool:
    roles = _role_ids(db, user.NguoiDungId)
    if roles.intersection({TRAINING_MANAGER_ROLE_ID, ADMIN_ROLE_ID}):
        return True
    role_names = (
        name.casefold()
        for (name,) in db.query(VaiTro.TenVaiTro)
        .join(NguoiDungVaiTro, NguoiDungVaiTro.VaiTroId == VaiTro.VaiTroId)
        .filter(NguoiDungVaiTro.NguoiDungId == user.NguoiDungId)
        .all()
    )
    return any("admin" in name or "quản trị" in name for name in role_names)


def _require_permission(db: Session, user: NguoiDung, code: str) -> None:
    if _is_manager(db, user) or _has_permission(db, user.NguoiDungId, code):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Bạn không có quyền thực hiện chức năng này.",
    )


def _get_lead_or_404(db: Session, lead_id: int) -> AdmissionsLead:
    lead = db.query(AdmissionsLead).filter(AdmissionsLead.LeadId == lead_id).first()
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy hồ sơ tư vấn.",
        )
    return lead


def _ensure_lead_scope(db: Session, user: NguoiDung, lead_id: int) -> None:
    if _is_manager(db, user):
        return
    assigned = (
        db.query(AdmissionsLeadAssignment.PhanCongId)
        .filter(
            AdmissionsLeadAssignment.LeadId == lead_id,
            AdmissionsLeadAssignment.NguoiDungId == user.NguoiDungId,
            _active_assignment_filter(),
        )
        .first()
    )
    if assigned is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không được phân công xử lý hồ sơ tư vấn này.",
        )


def _validate_program(db: Session, program_id: int | None) -> None:
    if program_id is None:
        return
    program = (
        db.query(ChuongTrinhDaoTao)
        .filter(ChuongTrinhDaoTao.ChuongTrinhId == program_id)
        .first()
    )
    if program is None or program.TrangThai != "Đang áp dụng":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Chương trình đào tạo không tồn tại hoặc đã ngừng áp dụng.",
        )


def _lead_payload(db: Session, lead: AdmissionsLead) -> dict:
    assignment_rows = (
        db.query(AdmissionsLeadAssignment, NguoiDung)
        .join(
            NguoiDung,
            NguoiDung.NguoiDungId == AdmissionsLeadAssignment.NguoiDungId,
        )
        .filter(AdmissionsLeadAssignment.LeadId == lead.LeadId)
        .order_by(AdmissionsLeadAssignment.NgayPhanCong)
        .all()
    )
    active_assignments = [
        (assignment, user)
        for assignment, user in assignment_rows
        if assignment.DangPhanCong
    ]
    assignment_actor_ids = {
        assignment.NguoiPhanCongId for assignment, _ in assignment_rows
    }
    assignment_actors = (
        {
            user.NguoiDungId: user.HoTen
            for user in db.query(NguoiDung)
            .filter(NguoiDung.NguoiDungId.in_(assignment_actor_ids))
            .all()
        }
        if assignment_actor_ids
        else {}
    )
    status_rows = (
        db.query(AdmissionsLeadStatusHistory, NguoiDung)
        .outerjoin(
            NguoiDung,
            NguoiDung.NguoiDungId
            == AdmissionsLeadStatusHistory.NguoiThucHienId,
        )
        .filter(AdmissionsLeadStatusHistory.LeadId == lead.LeadId)
        .order_by(AdmissionsLeadStatusHistory.ThoiDiem)
        .all()
    )
    interaction_rows = (
        db.query(AdmissionsLeadInteraction, NguoiDung)
        .outerjoin(
            NguoiDung,
            NguoiDung.NguoiDungId == AdmissionsLeadInteraction.NguoiThucHienId,
        )
        .filter(AdmissionsLeadInteraction.LeadId == lead.LeadId)
        .order_by(AdmissionsLeadInteraction.ThoiDiem.desc())
        .all()
    )
    conversion = (
        db.query(TuyenSinhLeadChuyenDoi)
        .filter(TuyenSinhLeadChuyenDoi.LeadId == lead.LeadId)
        .first()
    )
    program = (
        db.query(ChuongTrinhDaoTao)
        .filter(ChuongTrinhDaoTao.ChuongTrinhId == lead.ChuongTrinhId)
        .first()
        if lead.ChuongTrinhId is not None
        else None
    )
    now = business_now_naive()
    interactions = [
        {
            "tuongTacId": interaction.TuongTacId,
            "loai": interaction.Loai,
            "noiDung": interaction.NoiDung,
            "thoiDiem": interaction.ThoiDiem.isoformat(),
            "henGoiLaiLuc": (
                interaction.HenGoiLaiLuc.isoformat()
                if interaction.HenGoiLaiLuc
                else None
            ),
            "henGoiLaiQuaHan": (
                interaction.HenGoiLaiLuc is not None
                and interaction.HenGoiLaiLuc < now
                and lead.TrangThai not in TERMINAL_STATUSES
            ),
            "nguoiThucHien": actor.HoTen if actor else None,
        }
        for interaction, actor in interaction_rows
    ]
    return {
        "leadId": lead.LeadId,
        "hoTen": lead.HoTen,
        "soDienThoai": lead.SoDienThoai,
        "email": lead.Email,
        "nguon": lead.Nguon,
        "trangThai": lead.TrangThai,
        "hocVienId": conversion.NguoiDungId if conversion else None,
        "maHocVien": conversion.MaHocVien if conversion else None,
        "chuongTrinhId": lead.ChuongTrinhId,
        "tenChuongTrinh": program.TenChuongTrinh if program else None,
        "ghiChu": lead.GhiChu,
        "lyDoTuChoi": lead.LyDoTuChoi,
        "henGoiLaiQuaHan": any(
            item["henGoiLaiQuaHan"] for item in interactions
        ),
        "nguoiPhuTrach": [
            {
                "nguoiDungId": user.NguoiDungId,
                "hoTen": user.HoTen,
                "email": user.Email,
            }
            for _, user in active_assignments
        ],
        "ngayTao": lead.NgayTao.isoformat(),
        "lichSuBanGiao": [
            {
                "nguoiBanGiao": assignment_actors.get(
                    assignment.NguoiPhanCongId
                ),
                "nguoiNhan": user.HoTen,
                "thoiGian": assignment.NgayPhanCong.isoformat(),
                "ngayBoPhanCong": (
                    assignment.NgayBoPhanCong.isoformat()
                    if assignment.NgayBoPhanCong
                    else None
                ),
            }
            for assignment, user in assignment_rows
        ],
        "lichSuTrangThai": [
            {
                "trangThaiCu": item.TrangThaiCu,
                "trangThaiMoi": item.TrangThaiMoi,
                "lyDo": item.LyDo,
                "nguoiThucHien": actor.HoTen if actor else None,
                "thoiDiem": item.ThoiDiem.isoformat(),
            }
            for item, actor in status_rows
        ],
        "tuongTacs": interactions,
    }


def _apply_lead_status(
    db: Session,
    lead: AdmissionsLead,
    new_status: str,
    reason: str | None,
    actor_id: int,
    allow_enrolled: bool = False,
) -> None:
    if new_status not in VALID_STATUSES or (
        new_status == "Đã nhập học" and not allow_enrolled
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Trạng thái lead không hợp lệ.",
        )
    if lead.TrangThai in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead đã ở trạng thái kết thúc và không thể thay đổi.",
        )
    if (
        new_status != lead.TrangThai
        and new_status != "Đã nhập học"
        and new_status not in STATUS_TRANSITIONS.get(lead.TrangThai, set())
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể chuyển lead sang trạng thái này.",
        )
    if new_status == "Từ chối" and not (reason or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Vui lòng nhập lý do từ chối.",
        )
    if new_status != lead.TrangThai:
        db.add(
            AdmissionsLeadStatusHistory(
                LeadId=lead.LeadId,
                TrangThaiCu=lead.TrangThai,
                TrangThaiMoi=new_status,
                LyDo=reason.strip() if reason else None,
                NguoiThucHienId=actor_id,
                ThoiDiem=business_now_naive(),
            )
        )
    lead.TrangThai = new_status
    lead.LyDoTuChoi = reason.strip() if new_status == "Từ chối" and reason else None
    lead.NgayCapNhat = business_now_naive()


def _commit(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=message,
        ) from error


@router.get("/program-options")
def list_program_options(db: Session = Depends(get_db)):
    return [
        {
            "chuongTrinhId": program.ChuongTrinhId,
            "maChuongTrinh": program.MaChuongTrinh,
            "tenChuongTrinh": program.TenChuongTrinh,
        }
        for program in db.query(ChuongTrinhDaoTao)
        .filter(ChuongTrinhDaoTao.TrangThai == "Đang áp dụng")
        .order_by(ChuongTrinhDaoTao.TenChuongTrinh)
        .all()
    ]


@router.post("/public/leads", status_code=status.HTTP_201_CREATED)
def create_public_lead(
    request: PublicLeadWrite,
    db: Session = Depends(get_db),
):
    if request.website:
        return {"message": "Đã tiếp nhận thông tin tư vấn."}
    _validate_program(db, request.chuong_trinh_id)
    lead = AdmissionsLead(
        HoTen=request.ho_ten,
        SoDienThoai=request.so_dien_thoai,
        Email=str(request.email).lower() if request.email else None,
        Nguon=request.nguon,
        GhiChu=None,
        ChuongTrinhId=request.chuong_trinh_id,
        TrangThai="Mới",
        NgayTao=business_now_naive(),
        NgayCapNhat=business_now_naive(),
    )
    db.add(lead)
    _commit(db, "Không thể lưu yêu cầu tư vấn.")
    return {"message": "Đã tiếp nhận thông tin tư vấn."}


@router.get("/consultants")
def list_consultants(
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_permission(db, current_user, "LEAD_ASSIGN")
    return [
        {"nguoiDungId": user.NguoiDungId, "hoTen": user.HoTen, "email": user.Email}
        for user in (
            db.query(NguoiDung)
            .join(
                NguoiDungVaiTro,
                NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
            )
            .filter(
                NguoiDungVaiTro.VaiTroId == ADMISSIONS_ROLE_ID,
                NguoiDung.TrangThai == "HoatDong",
            )
            .order_by(NguoiDung.HoTen)
            .all()
        )
    ]


@router.get("/leads")
def list_leads(
    search: str | None = Query(default=None, max_length=255),
    lead_status: str | None = Query(default=None, alias="status", max_length=30),
    source: str | None = Query(default=None, max_length=100),
    assigned_user_id: int | None = Query(default=None, gt=0),
    unassigned: bool = Query(default=False),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_permission(db, current_user, "LEAD_VIEW")
    query = db.query(AdmissionsLead)
    if not _is_manager(db, current_user):
        query = query.join(
            AdmissionsLeadAssignment,
            AdmissionsLeadAssignment.LeadId == AdmissionsLead.LeadId,
        ).filter(
            AdmissionsLeadAssignment.NguoiDungId == current_user.NguoiDungId,
            _active_assignment_filter(),
        )
    if lead_status:
        query = query.filter(AdmissionsLead.TrangThai == lead_status)
    if source:
        query = query.filter(AdmissionsLead.Nguon == source)
    if assigned_user_id is not None:
        assigned_ids = db.query(AdmissionsLeadAssignment.LeadId).filter(
            AdmissionsLeadAssignment.NguoiDungId == assigned_user_id,
            _active_assignment_filter(),
        )
        query = query.filter(AdmissionsLead.LeadId.in_(assigned_ids))
    elif unassigned:
        assigned_ids = db.query(AdmissionsLeadAssignment.LeadId).filter(
            _active_assignment_filter()
        )
        query = query.filter(~AdmissionsLead.LeadId.in_(assigned_ids))
    if start_date:
        query = query.filter(AdmissionsLead.NgayTao >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(AdmissionsLead.NgayTao < datetime.combine(end_date + timedelta(days=1), datetime.min.time()))
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                AdmissionsLead.HoTen.ilike(term),
                AdmissionsLead.SoDienThoai.ilike(term),
                AdmissionsLead.Email.ilike(term),
                AdmissionsLead.GhiChu.ilike(term),
            )
        )
    leads = query.distinct().order_by(AdmissionsLead.NgayTao.desc()).all()
    return [_lead_payload(db, lead) for lead in leads]


@router.post("/leads", status_code=status.HTTP_201_CREATED)
def create_lead(
    request: LeadWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_permission(db, current_user, "LEAD_CREATE")
    _validate_program(db, request.chuong_trinh_id)
    if request.trang_thai == "Từ chối" and not request.ly_do_tu_choi:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Vui lòng nhập lý do từ chối.",
        )
    lead = AdmissionsLead(
        HoTen=request.ho_ten,
        SoDienThoai=request.so_dien_thoai,
        Email=str(request.email).lower() if request.email else None,
        Nguon=request.nguon,
        GhiChu=request.ghi_chu,
        ChuongTrinhId=request.chuong_trinh_id,
        TrangThai="Mới",
        NgayTao=business_now_naive(),
        NgayCapNhat=business_now_naive(),
        NguoiTaoId=current_user.NguoiDungId,
    )
    db.add(lead)
    db.flush()
    if not _is_manager(db, current_user):
        db.add(
            AdmissionsLeadAssignment(
                LeadId=lead.LeadId,
                NguoiDungId=current_user.NguoiDungId,
                NguoiPhanCongId=current_user.NguoiDungId,
                NgayPhanCong=business_now_naive(),
                DangPhanCong=True,
            )
        )
    if request.trang_thai != "Mới":
        _apply_lead_status(
            db,
            lead,
            request.trang_thai,
            request.ly_do_tu_choi,
            current_user.NguoiDungId,
        )
    _commit(db, "Không thể tạo lead do dữ liệu bị trùng hoặc không hợp lệ.")
    db.refresh(lead)
    return _lead_payload(db, lead)


@router.put("/leads/{lead_id}")
def update_lead(
    lead_id: int,
    request: LeadWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_permission(db, current_user, "LEAD_UPDATE")
    _ensure_lead_scope(db, current_user, lead_id)
    lead = _get_lead_or_404(db, lead_id)
    if lead.TrangThai in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead đã ở trạng thái kết thúc và không thể chỉnh sửa.",
        )
    _validate_program(db, request.chuong_trinh_id)
    lead.HoTen = request.ho_ten
    lead.SoDienThoai = request.so_dien_thoai
    lead.Email = str(request.email).lower() if request.email else None
    lead.Nguon = request.nguon
    lead.GhiChu = request.ghi_chu
    lead.ChuongTrinhId = request.chuong_trinh_id
    if request.trang_thai != lead.TrangThai:
        _apply_lead_status(
            db,
            lead,
            request.trang_thai,
            request.ly_do_tu_choi,
            current_user.NguoiDungId,
        )
    lead.NgayCapNhat = business_now_naive()
    _commit(db, "Không thể cập nhật lead.")
    return _lead_payload(db, lead)


def _replace_assignments(
    db: Session,
    lead_ids: list[int],
    consultant_ids: list[int],
    actor_id: int,
) -> None:
    if len(consultant_ids) != len(set(consultant_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Danh sách tư vấn viên không được trùng lặp.",
        )
    consultants = (
        db.query(NguoiDung.NguoiDungId)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(
            NguoiDung.NguoiDungId.in_(consultant_ids),
            NguoiDungVaiTro.VaiTroId == ADMISSIONS_ROLE_ID,
            NguoiDung.TrangThai == "HoatDong",
        )
        .all()
        if consultant_ids
        else []
    )
    if len(consultants) != len(consultant_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Có tư vấn viên không tồn tại hoặc đã ngừng hoạt động.",
        )
    now = business_now_naive()
    for lead_id in lead_ids:
        lead = _get_lead_or_404(db, lead_id)
        if lead.TrangThai in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Lead #{lead_id} đã kết thúc và không thể phân công.",
            )
        for assignment in (
            db.query(AdmissionsLeadAssignment)
            .filter(
                AdmissionsLeadAssignment.LeadId == lead_id,
                _active_assignment_filter(),
            )
            .with_for_update()
            .all()
        ):
            assignment.DangPhanCong = False
            assignment.NgayBoPhanCong = now
        for consultant_id in consultant_ids:
            db.add(
                AdmissionsLeadAssignment(
                    LeadId=lead_id,
                    NguoiDungId=consultant_id,
                    NguoiPhanCongId=actor_id,
                    NgayPhanCong=now,
                    DangPhanCong=True,
                )
            )
        lead.NgayCapNhat = now


@router.put("/leads/{lead_id}/assignments")
def assign_lead(
    lead_id: int,
    request: LeadAssignmentWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_permission(db, current_user, "LEAD_ASSIGN")
    _replace_assignments(
        db,
        [lead_id],
        request.consultant_ids,
        current_user.NguoiDungId,
    )
    _commit(db, "Không thể cập nhật phân công lead.")
    return _lead_payload(db, _get_lead_or_404(db, lead_id))


@router.put("/leads/bulk-assignments")
def bulk_assign_leads(
    request: LeadBulkAssignmentWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_permission(db, current_user, "LEAD_ASSIGN")
    if len(request.lead_ids) != len(set(request.lead_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Danh sách lead không được trùng lặp.",
        )
    _replace_assignments(
        db,
        request.lead_ids,
        request.consultant_ids,
        current_user.NguoiDungId,
    )
    _commit(db, "Không thể cập nhật phân công lead.")
    return {"message": "Đã cập nhật phân công lead."}


@router.delete("/leads/{lead_id}")
def delete_lead(
    lead_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_permission(db, current_user, "LEAD_DELETE")
    lead = _get_lead_or_404(db, lead_id)
    if db.query(TuyenSinhLeadChuyenDoi).filter(
        TuyenSinhLeadChuyenDoi.LeadId == lead_id
    ).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead đã chuyển thành học viên nên không thể xóa.",
        )
    db.delete(lead)
    _commit(db, "Lead đã có lịch sử hoặc tương tác nên không thể xóa.")
    return {"message": "Đã xóa lead."}


@router.post("/leads/{lead_id}/interactions", status_code=status.HTTP_201_CREATED)
def create_interaction(
    lead_id: int,
    request: LeadInteractionWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_permission(db, current_user, "LEAD_UPDATE")
    _ensure_lead_scope(db, current_user, lead_id)
    lead = _get_lead_or_404(db, lead_id)
    if lead.TrangThai in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead đã ở trạng thái kết thúc.",
        )
    if request.loai not in {"Gọi", "Nhắn tin", "Gặp"} or not request.noi_dung:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Loại hoặc nội dung tương tác không hợp lệ.",
        )
    interaction = AdmissionsLeadInteraction(
        LeadId=lead_id,
        Loai=request.loai,
        NoiDung=request.noi_dung,
        ThoiDiem=request.thoi_diem.replace(tzinfo=None),
        HenGoiLaiLuc=(
            request.hen_goi_lai_luc.replace(tzinfo=None)
            if request.hen_goi_lai_luc
            else None
        ),
        NguoiThucHienId=current_user.NguoiDungId,
        NgayTao=business_now_naive(),
    )
    db.add(interaction)
    lead.NgayCapNhat = business_now_naive()
    _commit(db, "Không thể ghi nhận tương tác.")
    return _lead_payload(db, lead)


@router.put("/leads/{lead_id}/status")
def update_lead_status(
    lead_id: int,
    request: LeadStatusWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_permission(db, current_user, "LEAD_UPDATE")
    _ensure_lead_scope(db, current_user, lead_id)
    lead = _get_lead_or_404(db, lead_id)
    _apply_lead_status(
        db,
        lead,
        request.trang_thai,
        request.ly_do_tu_choi,
        current_user.NguoiDungId,
    )
    _commit(db, "Không thể cập nhật trạng thái lead.")
    return _lead_payload(db, lead)


@router.post("/leads/{lead_id}/convert-to-student")
def convert_lead_to_student(
    lead_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_permission(db, current_user, "LEAD_UPDATE")
    _ensure_lead_scope(db, current_user, lead_id)
    lead = _get_lead_or_404(db, lead_id)
    existing = (
        db.query(TuyenSinhLeadChuyenDoi)
        .filter(TuyenSinhLeadChuyenDoi.LeadId == lead_id)
        .first()
    )
    if existing:
        return {
            "alreadyConverted": True,
            "maHocVien": existing.MaHocVien,
            "emailSent": None,
            "message": f"Lead đã được chuyển thành học viên {existing.MaHocVien}.",
        }
    if lead.TrangThai in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead đã ở trạng thái kết thúc.",
        )
    if not lead.Email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cần bổ sung email cho lead trước khi chuyển thành học viên.",
        )
    duplicate = db.query(NguoiDung).filter(NguoiDung.Email == lead.Email).first()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email đã được sử dụng bởi tài khoản khác.",
        )

    now = business_now_naive()
    temporary_password = secrets.token_urlsafe(18)
    user = NguoiDung(
        HoTen=lead.HoTen,
        Email=lead.Email,
        SoDienThoai=lead.SoDienThoai,
        MatKhauHash=password_hash.hash(temporary_password),
        TrangThai="HoatDong",
        DaKichHoat=False,
        BatBuocDoiMatKhau=True,
        CanDoiMatKhau=False,
        NgayTao=now,
        NgayCapNhat=now,
    )
    db.add(user)
    db.flush()
    db.add(
        NguoiDungVaiTro(
            NguoiDungId=user.NguoiDungId,
            VaiTroId=2,
            NgayGan=now,
        )
    )
    db.flush()
    student_code = f"HV{user.NguoiDungId:06d}"
    db.add(
        TuyenSinhLeadChuyenDoi(
            LeadId=lead_id,
            NguoiDungId=user.NguoiDungId,
            MaHocVien=student_code,
            ChuongTrinhId=lead.ChuongTrinhId,
            NgayNhapHoc=now,
            NguoiChuyenDoiId=current_user.NguoiDungId,
        )
    )
    _apply_lead_status(
        db,
        lead,
        "Đã nhập học",
        None,
        current_user.NguoiDungId,
    )
    raw_token = secrets.token_urlsafe(32)
    db.add(
        TokenKichHoat(
            NguoiDungId=user.NguoiDungId,
            Token=hashlib.sha256(raw_token.encode()).hexdigest(),
            ThoiGianTao=now,
            ThoiGianHetHan=now + timedelta(days=1),
            DaSuDung=False,
        )
    )
    _commit(db, "Không thể chuyển lead thành học viên.")

    activation_link = (
        f"{FRONTEND_URL.rstrip('/')}/activate-account?token={raw_token}"
    )
    try:
        send_activation_email(
            recipient_email=user.Email,
            ho_ten=user.HoTen,
            temporary_password=temporary_password,
            activation_link=activation_link,
        )
        email_sent = True
        message = f"Đã chuyển lead thành học viên {student_code} và gửi email kích hoạt."
    except RuntimeError:
        email_sent = False
        message = (
            f"Đã tạo học viên {student_code}, nhưng email kích hoạt chưa gửi được. "
            "Kiểm tra cấu hình SMTP và gửi lại email kích hoạt."
        )
    return {
        "alreadyConverted": False,
        "maHocVien": student_code,
        "emailSent": email_sent,
        "message": message,
    }
