from datetime import date, datetime, time, timedelta
import logging
import re
import time as monotonic_time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.admissions import Lead, LeadAssignmentHistory, LeadConversion
from app.models.lead_activity import LeadInteraction, LeadStatusHistory
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.schemas.admissions import (
    BulkLeadAssignmentsWrite,
    LeadAssignmentsWrite,
    LeadInteractionWrite,
    LeadStatusWrite,
    LeadWrite,
    PublicLeadCreate,
)
from app.services.academic_service import user_role_ids
from app.services.auth_service import prepare_student_account
from app.services.email_service import send_activation_email


router = APIRouter(prefix="/admissions", tags=["Admissions"])
logger = logging.getLogger(__name__)

TRAINING_MANAGER_ROLE_ID = 7
ADMIN_ROLE_ID = 8
ADMISSIONS_ROLE_ID = 5
PUBLIC_LEAD_RATE_LIMIT = 5
PUBLIC_LEAD_RATE_WINDOW_SECONDS = 60
_public_submissions: dict[str, list[float]] = {}
LEAD_STATUS_TRANSITIONS = {
    "Mới": {"Đã liên hệ", "Từ chối"},
    "Đã liên hệ": {"Đang tư vấn", "Từ chối"},
    "Đang tư vấn": {"Hẹn học thử", "Từ chối"},
    "Hẹn học thử": {"Chốt", "Từ chối"},
    "Chốt": set(),
    "Từ chối": set(),
    "Đang liên hệ": {"Đang tư vấn", "Hẹn học thử", "Chốt", "Từ chối"},
    "Tiềm năng": {"Hẹn học thử", "Chốt", "Từ chối"},
    "Đã chuyển đổi": set(),
    "Đã nhập học": set(),
    "Không tiềm năng": set(),
}
TERMINAL_LEAD_STATUSES = {"Từ chối", "Đã nhập học"}

THANK_YOU_MESSAGE = (
    "Cảm ơn bạn đã gửi thông tin. Bộ phận tư vấn sẽ liên hệ với bạn "
    "trong vòng 1 ngày làm việc."
)


def _phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def _local_naive(value: datetime) -> datetime:
    return value.astimezone().replace(tzinfo=None) if value.tzinfo else value


def _has_duplicate_phone(db: Session, phone: str, exclude_lead_id: int | None = None) -> bool:
    normalized = _phone_digits(phone)
    if not normalized:
        return False
    query = db.query(Lead)
    if exclude_lead_id is not None:
        query = query.filter(Lead.LeadId != exclude_lead_id)
    return any(_phone_digits(lead.SoDienThoai) == normalized for lead in query.all())


def _current_assignments(db: Session, lead_id: int) -> list[LeadAssignmentHistory]:
    return (
        db.query(LeadAssignmentHistory)
        .filter(
            LeadAssignmentHistory.LeadId == lead_id,
            LeadAssignmentHistory.DangPhanCong.in_([True]),
        )
        .order_by(
            LeadAssignmentHistory.NgayPhanCong,
            LeadAssignmentHistory.PhanCongId,
        )
        .all()
    )


def _lead_payload(db: Session, lead: Lead) -> dict:
    program = db.query(ChuongTrinhDaoTao).filter(
        ChuongTrinhDaoTao.ChuongTrinhId == lead.ChuongTrinhId
    ).first()
    active_assignments = _current_assignments(db, lead.LeadId)
    conversion = db.query(LeadConversion).filter(
        LeadConversion.LeadId == lead.LeadId
    ).first()
    return {
        "leadId": lead.LeadId,
        "hoTen": lead.HoTen,
        "soDienThoai": lead.SoDienThoai,
        "email": lead.Email,
        "nguon": lead.Nguon,
        "ghiChu": lead.GhiChu,
        "lyDoTuChoi": lead.LyDoTuChoi,
        "chuongTrinhId": lead.ChuongTrinhId,
        "maChuongTrinh": program.MaChuongTrinh if program else None,
        "tenChuongTrinh": program.TenChuongTrinh if program else None,
        "trangThai": lead.TrangThai,
        "hocVienId": conversion.NguoiDungId if conversion else None,
        "maHocVien": conversion.MaHocVien if conversion else None,
        "ngayTao": lead.NgayTao,
        "ngayCapNhat": lead.NgayCapNhat,
        "assignedUserIds": [row.NguoiDungId for row in active_assignments],
        "nguoiPhuTrach": [
            {
                "nguoiDungId": row.NguoiDungId,
                "hoTen": user.HoTen,
            }
            for row in active_assignments
            if (user := db.query(NguoiDung).filter(
                NguoiDung.NguoiDungId == row.NguoiDungId
            ).first()) is not None
        ],
        "assignedUsers": [
            {
                "nguoiDungId": row.NguoiDungId,
                "hoTen": user.HoTen,
            }
            for row in active_assignments
            if (user := db.query(NguoiDung).filter(
                NguoiDung.NguoiDungId == row.NguoiDungId
            ).first()) is not None
        ],
        "lichSuBanGiao": _handoff_history_payload(db, lead.LeadId),
        "lichSuTrangThai": _status_history_payload(db, lead.LeadId),
        "tuongTacs": _interactions_payload(db, lead.LeadId),
        "henGoiLaiQuaHan": _has_overdue_follow_up(db, lead.LeadId),
        "duplicatePhone": _has_duplicate_phone(
            db,
            lead.SoDienThoai,
            exclude_lead_id=lead.LeadId,
        ),
    }


def _status_history_payload(db: Session, lead_id: int) -> list[dict]:
    history = (
        db.query(LeadStatusHistory)
        .filter(LeadStatusHistory.LeadId == lead_id)
        .order_by(LeadStatusHistory.ThoiDiem, LeadStatusHistory.LichSuId)
        .all()
    )
    user_ids = {entry.NguoiThucHienId for entry in history}
    users = {
        user.NguoiDungId: user.HoTen
        for user in db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId.in_(user_ids))
        .all()
    } if user_ids else {}
    return [
        {
            "trangThaiCu": entry.TrangThaiCu,
            "trangThaiMoi": entry.TrangThaiMoi,
            "lyDo": entry.LyDo,
            "nguoiThucHien": users.get(entry.NguoiThucHienId),
            "thoiDiem": entry.ThoiDiem,
        }
        for entry in history
    ]


def _interactions_payload(db: Session, lead_id: int) -> list[dict]:
    entries = (
        db.query(LeadInteraction)
        .filter(LeadInteraction.LeadId == lead_id)
        .order_by(LeadInteraction.ThoiDiem.desc(), LeadInteraction.TuongTacId.desc())
        .all()
    )
    user_ids = {entry.NguoiThucHienId for entry in entries}
    users = {
        user.NguoiDungId: user.HoTen
        for user in db.query(NguoiDung)
        .filter(NguoiDung.NguoiDungId.in_(user_ids))
        .all()
    } if user_ids else {}
    now = datetime.now()
    later_activity_times = [entry.ThoiDiem for entry in entries]
    payload = []
    for entry in entries:
        overdue = (
            entry.HenGoiLaiLuc is not None
            and entry.HenGoiLaiLuc < now
            and not any(
                happened_at >= entry.HenGoiLaiLuc
                for happened_at in later_activity_times
                if happened_at > entry.ThoiDiem
            )
        )
        payload.append(
            {
                "tuongTacId": entry.TuongTacId,
                "loai": entry.Loai,
                "noiDung": entry.NoiDung,
                "thoiDiem": entry.ThoiDiem,
                "henGoiLaiLuc": entry.HenGoiLaiLuc,
                "henGoiLaiQuaHan": overdue,
                "nguoiThucHien": users.get(entry.NguoiThucHienId),
            }
        )
    return payload


def _has_overdue_follow_up(db: Session, lead_id: int) -> bool:
    return any(
        item["henGoiLaiQuaHan"]
        for item in _interactions_payload(db, lead_id)
    )


def _validate_status_transition(current: str, target: str) -> None:
    if current == target:
        return
    if target not in LEAD_STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Không thể chuyển trạng thái từ “{current}” sang “{target}”.",
        )


def _record_status_change(
    db: Session,
    lead: Lead,
    new_status: str,
    actor_id: int,
    reason: str | None = None,
) -> None:
    db.add(
        LeadStatusHistory(
            LeadId=lead.LeadId,
            TrangThaiCu=lead.TrangThai,
            TrangThaiMoi=new_status,
            LyDo=reason,
            NguoiThucHienId=actor_id,
            ThoiDiem=datetime.now(),
        )
    )


def _get_visible_lead(
    db: Session,
    lead_id: int,
    user: NguoiDung,
) -> Lead:
    lead = db.query(Lead).filter(Lead.LeadId == lead_id).first()
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy khách hàng tiềm năng.",
        )
    roles = user_role_ids(db, user.NguoiDungId)
    if roles.intersection({TRAINING_MANAGER_ROLE_ID, ADMIN_ROLE_ID}):
        return lead
    assigned = (
        db.query(LeadAssignmentHistory.PhanCongId)
        .filter(
            LeadAssignmentHistory.LeadId == lead_id,
            LeadAssignmentHistory.NguoiDungId == user.NguoiDungId,
            LeadAssignmentHistory.DangPhanCong.in_([True]),
        )
        .first()
    )
    if ADMISSIONS_ROLE_ID not in roles or assigned is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy khách hàng tiềm năng.",
        )
    return lead


def _handoff_history_payload(db: Session, lead_id: int) -> list[dict]:
    assignments = (
        db.query(LeadAssignmentHistory)
        .filter(LeadAssignmentHistory.LeadId == lead_id)
        .order_by(
            LeadAssignmentHistory.NgayPhanCong,
            LeadAssignmentHistory.PhanCongId,
        )
        .all()
    )
    history = []
    for assignment in assignments:
        sender = db.query(NguoiDung).filter(
            NguoiDung.NguoiDungId == assignment.NguoiPhanCongId
        ).first()
        receiver = db.query(NguoiDung).filter(
            NguoiDung.NguoiDungId == assignment.NguoiDungId
        ).first()
        history.append(
            {
                "nguoiBanGiao": sender.HoTen if sender else None,
                "nguoiNhan": receiver.HoTen if receiver else None,
                "nguoiBanGiaoId": assignment.NguoiPhanCongId,
                "nguoiNhanId": assignment.NguoiDungId,
                "thoiGian": assignment.NgayPhanCong,
                "ngayBoPhanCong": assignment.NgayBoPhanCong,
            }
        )
    return history


def _get_active_program_or_422(db: Session, program_id: int) -> ChuongTrinhDaoTao:
    program = db.query(ChuongTrinhDaoTao).filter(
        ChuongTrinhDaoTao.ChuongTrinhId == program_id,
        ChuongTrinhDaoTao.TrangThai == "Đang áp dụng",
    ).first()
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Chương trình không tồn tại hoặc đã ngừng áp dụng.",
        )
    return program


def _validate_consultants(db: Session, user_ids: list[int]) -> None:
    if not user_ids:
        return
    users = (
        db.query(NguoiDung.NguoiDungId)
        .join(
            NguoiDungVaiTro,
            NguoiDungVaiTro.NguoiDungId == NguoiDung.NguoiDungId,
        )
        .filter(
            NguoiDung.NguoiDungId.in_(user_ids),
            NguoiDungVaiTro.VaiTroId == ADMISSIONS_ROLE_ID,
            NguoiDung.TrangThai == "HoatDong",
        )
        .all()
    )
    if {user_id for (user_id,) in users} != set(user_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Có tư vấn viên không tồn tại, chưa hoạt động hoặc không thuộc vai trò tuyển sinh.",
        )


def _commit(db: Session, error_detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail,
        ) from error


def _create_lead(
    db: Session,
    *,
    name: str,
    phone: str,
    email: str | None,
    source: str,
    note: str | None = None,
    program_id: int | None,
    status_value: str,
    creator: NguoiDung | None,
) -> Lead:
    if program_id is not None:
        _get_active_program_or_422(db, program_id)
    now = datetime.now()
    lead = Lead(
        HoTen=name.strip(),
        SoDienThoai=phone.strip(),
        Email=email,
        Nguon=source.strip(),
        GhiChu=note,
        ChuongTrinhId=program_id,
        TrangThai=status_value,
        NgayTao=now,
        NgayCapNhat=now,
        NguoiTaoId=creator.NguoiDungId if creator else None,
    )
    db.add(lead)
    db.flush()
    if creator is not None and ADMISSIONS_ROLE_ID in user_role_ids(db, creator.NguoiDungId):
        db.add(
            LeadAssignmentHistory(
                LeadId=lead.LeadId,
                NguoiDungId=creator.NguoiDungId,
                NguoiPhanCongId=creator.NguoiDungId,
                NgayPhanCong=now,
                DangPhanCong=True,
            )
        )
    return lead


@router.get("/program-options")
def public_program_options(db: Session = Depends(get_db)):
    programs = (
        db.query(ChuongTrinhDaoTao)
        .filter(ChuongTrinhDaoTao.TrangThai == "Đang áp dụng")
        .order_by(ChuongTrinhDaoTao.TenChuongTrinh)
        .all()
    )
    return [
        {
            "chuongTrinhId": program.ChuongTrinhId,
            "maChuongTrinh": program.MaChuongTrinh,
            "tenChuongTrinh": program.TenChuongTrinh,
        }
        for program in programs
    ]


@router.post(
    "/public/leads",
    status_code=status.HTTP_201_CREATED,
)
def submit_public_lead(
    request: PublicLeadCreate,
    http_request: Request,
    db: Session = Depends(get_db),
):
    now = monotonic_time.monotonic()
    client_ip = http_request.client.host if http_request.client else "unknown"
    recent = [
        submitted_at
        for submitted_at in _public_submissions.get(client_ip, [])
        if now - submitted_at < PUBLIC_LEAD_RATE_WINDOW_SECONDS
    ]
    if len(recent) >= PUBLIC_LEAD_RATE_LIMIT:
        _public_submissions[client_ip] = recent
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Đã nhận quá nhiều yêu cầu. Vui lòng thử lại sau.",
        )
    recent.append(now)
    _public_submissions[client_ip] = recent

    # A populated honeypot receives the normal response but is never persisted.
    if request.website:
        return {
            "message": THANK_YOU_MESSAGE,
            "responseTimeAssurance": "Trong vòng 1 ngày làm việc.",
        }
    lead = _create_lead(
        db,
        name=request.ho_ten,
        phone=request.so_dien_thoai,
        email=request.email,
        source=request.nguon,
        note=None,
        program_id=request.chuong_trinh_id,
        status_value="Mới",
        creator=None,
    )
    _commit(db, "Không thể ghi nhận yêu cầu tư vấn.")
    return {
        "message": THANK_YOU_MESSAGE,
        "responseTimeAssurance": "Trong vòng 1 ngày làm việc.",
        "duplicatePhone": _has_duplicate_phone(
            db,
            lead.SoDienThoai,
            exclude_lead_id=lead.LeadId,
        ),
    }


@router.get(
    "/consultants",
    dependencies=[Depends(require_permission("LEAD_ASSIGN"))],
)
def list_admissions_consultants(db: Session = Depends(get_db)):
    users = (
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
    return [
        {
            "nguoiDungId": user.NguoiDungId,
            "hoTen": user.HoTen,
            "email": user.Email,
            "soDienThoai": user.SoDienThoai,
        }
        for user in users
    ]


@router.get(
    "/leads",
    dependencies=[Depends(require_permission("LEAD_VIEW"))],
)
def list_leads(
    status_filter: str | None = Query(default=None, alias="status"),
    source: str | None = Query(default=None),
    assigned_user_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    search: str | None = Query(default=None),
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = user_role_ids(db, current_user.NguoiDungId)
    query = db.query(Lead)
    if not roles.intersection({TRAINING_MANAGER_ROLE_ID, ADMIN_ROLE_ID}):
        if ADMISSIONS_ROLE_ID not in roles:
            raise HTTPException(status_code=403, detail="Không có quyền xem khách hàng tiềm năng.")
        assigned_lead_ids = (
            db.query(LeadAssignmentHistory.LeadId)
            .filter(
                LeadAssignmentHistory.NguoiDungId == current_user.NguoiDungId,
                LeadAssignmentHistory.DangPhanCong.in_([True]),
            )
        )
        query = query.filter(Lead.LeadId.in_(assigned_lead_ids))
    if status_filter:
        query = query.filter(Lead.TrangThai == status_filter)
    if source:
        query = query.filter(Lead.Nguon == source)
    if assigned_user_id is not None:
        assigned_lead_ids = (
            db.query(LeadAssignmentHistory.LeadId)
            .filter(
                LeadAssignmentHistory.NguoiDungId == assigned_user_id,
                LeadAssignmentHistory.DangPhanCong.in_([True]),
            )
        )
        query = query.filter(Lead.LeadId.in_(assigned_lead_ids))
    if start_date:
        query = query.filter(Lead.NgayTao >= datetime.combine(start_date, time.min))
    if end_date:
        query = query.filter(
            Lead.NgayTao < datetime.combine(end_date + timedelta(days=1), time.min)
        )
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Lead.HoTen.ilike(term),
                Lead.SoDienThoai.ilike(term),
                Lead.Email.ilike(term),
            )
        )
    return [
        _lead_payload(db, lead)
        for lead in query.distinct().order_by(Lead.NgayTao.desc(), Lead.LeadId.desc()).all()
    ]


@router.post(
    "/leads",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("LEAD_CREATE"))],
)
def create_lead(
    request: LeadWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if request.trang_thai != "Mới":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Lead mới phải bắt đầu ở trạng thái Mới.",
        )
    lead = _create_lead(
        db,
        name=request.ho_ten,
        phone=request.so_dien_thoai,
        email=request.email,
        source=request.nguon,
        note=request.ghi_chu,
        program_id=request.chuong_trinh_id,
        status_value=request.trang_thai,
        creator=current_user,
    )
    lead.LyDoTuChoi = request.ly_do_tu_choi
    db.add(
        LeadStatusHistory(
            LeadId=lead.LeadId,
            TrangThaiCu=None,
            TrangThaiMoi=lead.TrangThai,
            LyDo=request.ly_do_tu_choi,
            NguoiThucHienId=current_user.NguoiDungId,
            ThoiDiem=datetime.now(),
        )
    )
    _commit(db, "Không thể tạo khách hàng tiềm năng.")
    return _lead_payload(db, lead)


@router.put(
    "/leads/bulk-assignments",
    dependencies=[Depends(require_permission("LEAD_ASSIGN"))],
)
def bulk_assign_leads(
    request: BulkLeadAssignmentsWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = user_role_ids(db, current_user.NguoiDungId)
    if not roles.intersection({TRAINING_MANAGER_ROLE_ID, ADMIN_ROLE_ID}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ quản lý đào tạo hoặc quản trị viên được phân công tư vấn viên.",
        )
    leads = db.query(Lead).filter(Lead.LeadId.in_(request.lead_ids)).all()
    if len(leads) != len(request.lead_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Một hoặc nhiều khách hàng tiềm năng không tồn tại.",
        )
    if any(lead.TrangThai in TERMINAL_LEAD_STATUSES for lead in leads):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể phân công lead đã kết thúc quy trình.",
        )
    _validate_consultants(db, request.consultant_ids)
    now = datetime.now()
    desired_ids = set(request.consultant_ids)
    for lead in leads:
        current_rows = _current_assignments(db, lead.LeadId)
        current_ids = {row.NguoiDungId for row in current_rows}
        for assignment in current_rows:
            if assignment.NguoiDungId not in desired_ids:
                assignment.DangPhanCong = False
                assignment.NgayBoPhanCong = now
        for user_id in sorted(desired_ids - current_ids):
            db.add(
                LeadAssignmentHistory(
                    LeadId=lead.LeadId,
                    NguoiDungId=user_id,
                    NguoiPhanCongId=current_user.NguoiDungId,
                    NgayPhanCong=now,
                    DangPhanCong=True,
                )
            )
        lead.NgayCapNhat = now
    _commit(db, "Không thể lưu phân công hàng loạt.")
    return {
        "message": f"Đã phân công {len(leads)} khách hàng tiềm năng.",
        "leadIds": request.lead_ids,
        "consultantIds": sorted(desired_ids),
    }


@router.get(
    "/leads/{lead_id}",
    dependencies=[Depends(require_permission("LEAD_VIEW"))],
)
def get_lead(
    lead_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _lead_payload(db, _get_visible_lead(db, lead_id, current_user))


@router.put(
    "/leads/{lead_id}",
    dependencies=[Depends(require_permission("LEAD_UPDATE"))],
)
def update_lead(
    lead_id: int,
    request: LeadWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lead = _get_visible_lead(db, lead_id, current_user)
    if lead.TrangThai in TERMINAL_LEAD_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead đã kết thúc quy trình và không thể chỉnh sửa.",
        )
    if request.trang_thai == "Đã nhập học":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Chỉ có thể chuyển lead sang trạng thái nhập học bằng thao tác chuyển đổi.",
        )
    if request.chuong_trinh_id is not None:
        _get_active_program_or_422(db, request.chuong_trinh_id)
    _validate_status_transition(lead.TrangThai, request.trang_thai)
    if request.trang_thai != lead.TrangThai:
        _record_status_change(
            db,
            lead,
            request.trang_thai,
            current_user.NguoiDungId,
            request.ly_do_tu_choi,
        )
    lead.HoTen = request.ho_ten.strip()
    lead.SoDienThoai = request.so_dien_thoai.strip()
    lead.Email = request.email
    lead.Nguon = request.nguon.strip()
    lead.GhiChu = request.ghi_chu
    lead.LyDoTuChoi = request.ly_do_tu_choi
    lead.ChuongTrinhId = request.chuong_trinh_id
    lead.TrangThai = request.trang_thai
    lead.NgayCapNhat = datetime.now()
    _commit(db, "Không thể cập nhật khách hàng tiềm năng.")
    return _lead_payload(db, lead)


@router.put(
    "/leads/{lead_id}/status",
    dependencies=[Depends(require_permission("LEAD_UPDATE"))],
)
def update_lead_status(
    lead_id: int,
    request: LeadStatusWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lead = _get_visible_lead(db, lead_id, current_user)
    if lead.TrangThai in TERMINAL_LEAD_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead đã kết thúc quy trình và không thể đổi trạng thái.",
        )
    if request.trang_thai in {"Đã nhập học", "Đã chuyển đổi"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Chỉ có thể ghi nhận nhập học qua thao tác chuyển lead thành học viên.",
        )
    _validate_status_transition(lead.TrangThai, request.trang_thai)
    if request.trang_thai != lead.TrangThai:
        _record_status_change(
            db,
            lead,
            request.trang_thai,
            current_user.NguoiDungId,
            request.ly_do_tu_choi,
        )
    lead.TrangThai = request.trang_thai
    lead.LyDoTuChoi = request.ly_do_tu_choi if request.trang_thai == "Từ chối" else None
    lead.NgayCapNhat = datetime.now()
    _commit(db, "Không thể cập nhật trạng thái khách hàng tiềm năng.")
    return _lead_payload(db, lead)


@router.get(
    "/leads/{lead_id}/interactions",
    dependencies=[Depends(require_permission("LEAD_VIEW"))],
)
def list_lead_interactions(
    lead_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_visible_lead(db, lead_id, current_user)
    return _interactions_payload(db, lead_id)


@router.post(
    "/leads/{lead_id}/interactions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("LEAD_UPDATE"))],
)
def create_lead_interaction(
    lead_id: int,
    request: LeadInteractionWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lead = _get_visible_lead(db, lead_id, current_user)
    if lead.TrangThai in TERMINAL_LEAD_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể ghi tương tác cho lead đã kết thúc.",
        )
    happened_at = _local_naive(request.thoi_diem) if request.thoi_diem else datetime.now()
    follow_up_at = (
        _local_naive(request.hen_goi_lai_luc)
        if request.hen_goi_lai_luc
        else None
    )
    if follow_up_at and follow_up_at < happened_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Thời điểm gọi lại phải sau thời điểm tương tác.",
        )
    interaction = LeadInteraction(
        LeadId=lead.LeadId,
        Loai=request.loai,
        NoiDung=request.noi_dung,
        ThoiDiem=happened_at,
        HenGoiLaiLuc=follow_up_at,
        NguoiThucHienId=current_user.NguoiDungId,
        NgayTao=datetime.now(),
    )
    db.add(interaction)
    lead.NgayCapNhat = datetime.now()
    _commit(db, "Không thể ghi nhật ký tương tác.")
    return next(
        item
        for item in _interactions_payload(db, lead_id)
        if item["tuongTacId"] == interaction.TuongTacId
    )


@router.post(
    "/leads/{lead_id}/convert-to-student",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("LEAD_UPDATE"))],
)
def convert_lead_to_student(
    lead_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lead = (
        db.query(Lead)
        .filter(Lead.LeadId == lead_id)
        .with_for_update()
        .first()
    )
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy khách hàng tiềm năng.",
        )
    _get_visible_lead(db, lead_id, current_user)

    conversion = db.query(LeadConversion).filter(
        LeadConversion.LeadId == lead_id
    ).first()
    if conversion is not None:
        return {
            "alreadyConverted": True,
            "emailSent": None,
            "hocVienId": conversion.NguoiDungId,
            "maHocVien": conversion.MaHocVien,
            "email": db.query(NguoiDung.Email).filter(
                NguoiDung.NguoiDungId == conversion.NguoiDungId
            ).scalar(),
            "lead": _lead_payload(db, lead),
            "message": "Lead này đã được chuyển thành học viên trước đó.",
        }

    if lead.TrangThai in TERMINAL_LEAD_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lead đã kết thúc quy trình và không thể chuyển đổi.",
        )
    if not lead.Email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cần bổ sung email hợp lệ cho lead trước khi tạo tài khoản học viên.",
        )
    if len(lead.SoDienThoai) > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Số điện thoại dài quá 20 ký tự và không thể lưu vào hồ sơ người dùng.",
        )
    if db.query(NguoiDung).filter(NguoiDung.Email == lead.Email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email này đã được sử dụng cho một tài khoản khác. Hãy kiểm tra email của lead.",
        )

    now = datetime.now()
    try:
        user, temporary_password, activation_link = (
            prepare_student_account(
                db,
                ho_ten=lead.HoTen,
                email=lead.Email,
                so_dien_thoai=lead.SoDienThoai,
                now=now,
            )
        )
        ma_hoc_vien = f"HV{user.NguoiDungId:06d}"
        db.add(
            LeadConversion(
                LeadId=lead.LeadId,
                NguoiDungId=user.NguoiDungId,
                MaHocVien=ma_hoc_vien,
                ChuongTrinhId=lead.ChuongTrinhId,
                NgayNhapHoc=now,
                NguoiChuyenDoiId=current_user.NguoiDungId,
            )
        )
        _record_status_change(
            db,
            lead,
            "Đã nhập học",
            current_user.NguoiDungId,
        )
        lead.TrangThai = "Đã nhập học"
        lead.LyDoTuChoi = None
        lead.NgayCapNhat = now

        send_activation_email(
            recipient_email=user.Email,
            ho_ten=user.HoTen,
            temporary_password=temporary_password,
            activation_link=activation_link,
            ma_hoc_vien=ma_hoc_vien,
        )
        db.commit()
        db.refresh(lead)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        logger.exception("Lead conversion conflicted for lead %s", lead_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể chuyển đổi do email hoặc hồ sơ học viên đã tồn tại.",
        ) from error
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("Database error converting lead %s", lead_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể lưu hồ sơ học viên và trạng thái lead.",
        ) from error
    except RuntimeError as error:
        db.rollback()
        logger.exception("Could not send student activation for lead %s", lead_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Không thể gửi email kích hoạt; chưa tạo hồ sơ học viên. {error}",
        ) from error

    return {
        "alreadyConverted": False,
        "emailSent": True,
        "hocVienId": user.NguoiDungId,
        "maHocVien": ma_hoc_vien,
        "email": user.Email,
        "lead": _lead_payload(db, lead),
        "message": f"Đã nhập học thành công. Mã học viên: {ma_hoc_vien}. Email kích hoạt đã được gửi.",
    }


@router.delete(
    "/leads/{lead_id}",
    dependencies=[Depends(require_permission("LEAD_DELETE"))],
)
def delete_lead(
    lead_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = user_role_ids(db, current_user.NguoiDungId)
    if not roles.intersection({TRAINING_MANAGER_ROLE_ID, ADMIN_ROLE_ID}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ quản lý đào tạo hoặc quản trị viên được xóa khách hàng tiềm năng.",
        )
    lead = db.query(Lead).filter(Lead.LeadId == lead_id).first()
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy khách hàng tiềm năng.",
        )
    if lead.TrangThai in TERMINAL_LEAD_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể xóa lead đã kết thúc quy trình.",
        )
    db.query(LeadAssignmentHistory).filter(
        LeadAssignmentHistory.LeadId == lead_id
    ).delete(synchronize_session=False)
    db.query(LeadInteraction).filter(
        LeadInteraction.LeadId == lead_id
    ).delete(synchronize_session=False)
    db.query(LeadStatusHistory).filter(
        LeadStatusHistory.LeadId == lead_id
    ).delete(synchronize_session=False)
    db.delete(lead)
    _commit(db, "Không thể xóa khách hàng tiềm năng.")
    return {"message": "Đã xóa khách hàng tiềm năng."}


@router.get(
    "/leads/{lead_id}/assignments",
    dependencies=[Depends(require_permission("LEAD_VIEW"))],
)
def get_lead_assignments(
    lead_id: int,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_visible_lead(db, lead_id, current_user)
    assignments = (
        db.query(LeadAssignmentHistory)
        .filter(LeadAssignmentHistory.LeadId == lead_id)
        .order_by(LeadAssignmentHistory.NgayPhanCong.desc())
        .all()
    )
    result = []
    for assignment in assignments:
        consultant = db.query(NguoiDung).filter(
            NguoiDung.NguoiDungId == assignment.NguoiDungId
        ).first()
        assigner = db.query(NguoiDung).filter(
            NguoiDung.NguoiDungId == assignment.NguoiPhanCongId
        ).first()
        result.append({
            "phanCongId": assignment.PhanCongId,
            "nguoiDungId": assignment.NguoiDungId,
            "hoTen": consultant.HoTen if consultant else None,
            "nguoiPhanCongId": assignment.NguoiPhanCongId,
            "nguoiPhanCong": assigner.HoTen if assigner else None,
            "ngayPhanCong": assignment.NgayPhanCong,
            "ngayBoPhanCong": assignment.NgayBoPhanCong,
            "dangPhanCong": assignment.DangPhanCong,
        })
    return result


@router.put(
    "/leads/{lead_id}/assignments",
    dependencies=[Depends(require_permission("LEAD_ASSIGN"))],
)
def replace_lead_assignments(
    lead_id: int,
    request: LeadAssignmentsWrite,
    current_user: NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = user_role_ids(db, current_user.NguoiDungId)
    if not roles.intersection({TRAINING_MANAGER_ROLE_ID, ADMIN_ROLE_ID}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ quản lý đào tạo hoặc quản trị viên được phân công tư vấn viên.",
        )
    lead = db.query(Lead).filter(Lead.LeadId == lead_id).first()
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy khách hàng tiềm năng.",
        )
    if lead.TrangThai in TERMINAL_LEAD_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không thể phân công lead đã kết thúc quy trình.",
        )
    _validate_consultants(db, request.assigned_user_ids)
    now = datetime.now()
    current_rows = _current_assignments(db, lead_id)
    current_ids = {row.NguoiDungId for row in current_rows}
    desired_ids = set(request.assigned_user_ids)
    for assignment in current_rows:
        if assignment.NguoiDungId not in desired_ids:
            assignment.DangPhanCong = False
            assignment.NgayBoPhanCong = now
    for user_id in sorted(desired_ids - current_ids):
        db.add(
            LeadAssignmentHistory(
                LeadId=lead_id,
                NguoiDungId=user_id,
                NguoiPhanCongId=current_user.NguoiDungId,
                NgayPhanCong=now,
                DangPhanCong=True,
            )
        )
    lead.NgayCapNhat = now
    _commit(db, "Không thể lưu phân công tư vấn.")
    return {
        "leadId": lead_id,
        "assignedUserIds": sorted(desired_ids),
        "consultantIds": sorted(desired_ids),
        "assignmentHistory": get_lead_assignments(lead_id, current_user, db),
    }
