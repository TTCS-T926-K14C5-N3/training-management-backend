import json
import logging
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.lich_hoc_thong_bao import LichHocThongBao
from app.models.nguoi_dung import NguoiDung
from app.services.email_service import send_schedule_change_email
from app.services.business_time import business_now


logger = logging.getLogger(__name__)
MAX_NOTIFICATION_ATTEMPTS = 3
STALE_DELIVERY_AFTER = timedelta(minutes=5)


def queue_schedule_notifications(
    db: Session,
    *,
    schedule_id: int,
    event_type: str,
    before: dict,
    after: dict,
    reason: str | None,
    actor_id: int,
    occurred_at: datetime,
    recipient_ids: set[int],
) -> str | None:
    if not recipient_ids:
        return None

    event_id = str(uuid4())
    before_json = json.dumps(before, ensure_ascii=False, separators=(",", ":"))
    after_json = json.dumps(after, ensure_ascii=False, separators=(",", ":"))
    message = _notification_message(
        event_type,
        before,
        after,
        reason,
    )
    db.add_all(
        LichHocThongBao(
            SuKienId=event_id,
            LichHocId=schedule_id,
            NguoiNhanId=recipient_id,
            LoaiSuKien=event_type,
            NoiDung=message,
            DuLieuCu=before_json,
            DuLieuMoi=after_json,
            LyDo=reason,
            NguoiThucHienId=actor_id,
            ThoiDiemPhatSinh=occurred_at,
            TrangThai="Chờ gửi",
            SoLanGui=0,
        )
        for recipient_id in sorted(recipient_ids)
    )
    return event_id


def _notification_message(
    event_type: str,
    before: dict,
    after: dict,
    reason: str | None,
) -> str:
    schedule_code = after.get("maBuoiHoc") or before.get("maBuoiHoc")
    if event_type == "Hủy buổi học":
        return (
            f"Buổi học {schedule_code} đã bị hủy. "
            f"Lý do: {reason or 'Không có thông tin'}"
        )

    return (
        f"Buổi học {schedule_code} đã thay đổi lịch. "
        f"Trước: {_schedule_summary(before)}. "
        f"Sau: {_schedule_summary(after)}."
    )


def _schedule_summary(schedule: dict) -> str:
    return (
        f"{schedule.get('ngayHoc')} "
        f"{schedule.get('gioBatDau')}-{schedule.get('gioKetThuc')}, "
        f"phòng {schedule.get('tenPhong') or schedule.get('maPhong') or 'chưa rõ'}, "
        f"giảng viên {schedule.get('giangVienTen') or 'chưa rõ'}"
    )


def process_schedule_notifications(
    db: Session,
    *,
    event_id: str | None = None,
    retry_failed: bool = False,
    limit: int = 100,
) -> dict[str, int]:
    now = business_now()
    stale_before = now - STALE_DELIVERY_AFTER
    stale_exhausted = db.query(LichHocThongBao).filter(
        LichHocThongBao.TrangThai == "Đang gửi",
        LichHocThongBao.ThoiDiemGuiCuoi <= stale_before,
        LichHocThongBao.SoLanGui >= MAX_NOTIFICATION_ATTEMPTS,
    )
    if event_id is not None:
        stale_exhausted = stale_exhausted.filter(
            LichHocThongBao.SuKienId == event_id
        )
    stale_exhausted.update(
        {
            LichHocThongBao.TrangThai: "Thất bại",
            LichHocThongBao.LoiGui: (
                "Đã hết số lần gửi tối đa sau khi tiến trình bị gián đoạn."
            ),
        },
        synchronize_session=False,
    )
    db.commit()

    eligible_states = [
        LichHocThongBao.TrangThai == "Chờ gửi",
        and_(
            LichHocThongBao.TrangThai == "Đang gửi",
            LichHocThongBao.ThoiDiemGuiCuoi <= stale_before,
        ),
    ]
    if retry_failed:
        eligible_states.append(
            LichHocThongBao.TrangThai == "Thất bại"
        )

    query = (
        db.query(LichHocThongBao)
        .filter(
            LichHocThongBao.SoLanGui < MAX_NOTIFICATION_ATTEMPTS,
            or_(*eligible_states),
        )
    )
    if event_id is not None:
        query = query.filter(LichHocThongBao.SuKienId == event_id)
    notification_ids = [
        notification_id
        for (notification_id,) in query.with_entities(
            LichHocThongBao.LichHocThongBaoId
        )
        .order_by(LichHocThongBao.LichHocThongBaoId)
        .limit(limit)
        .all()
    ]

    sent_count = 0
    failed_count = 0
    processed_count = 0
    for notification_id in notification_ids:
        claim = db.query(LichHocThongBao).filter(
            LichHocThongBao.LichHocThongBaoId == notification_id,
            LichHocThongBao.SoLanGui < MAX_NOTIFICATION_ATTEMPTS,
            or_(*eligible_states),
        )
        claimed_count = claim.update(
            {
                LichHocThongBao.TrangThai: "Đang gửi",
                LichHocThongBao.SoLanGui: LichHocThongBao.SoLanGui + 1,
                LichHocThongBao.ThoiDiemGuiCuoi: business_now(),
                LichHocThongBao.LoiGui: None,
            },
            synchronize_session=False,
        )
        db.commit()
        if claimed_count != 1:
            continue
        processed_count += 1
        notification = (
            db.query(LichHocThongBao)
            .filter(LichHocThongBao.LichHocThongBaoId == notification_id)
            .one()
        )

        recipient = (
            db.query(NguoiDung)
            .filter(NguoiDung.NguoiDungId == notification.NguoiNhanId)
            .first()
        )
        try:
            if recipient is None:
                raise RuntimeError("Không tìm thấy người nhận thông báo.")
            send_schedule_change_email(
                recipient.Email,
                recipient.HoTen,
                notification.NoiDung,
            )
        except (RuntimeError, ValueError) as error:
            notification.TrangThai = "Thất bại"
            notification.LoiGui = str(error)[:2000]
            db.commit()
            logger.warning(
                "Schedule notification %s failed on attempt %s: %s",
                notification.LichHocThongBaoId,
                notification.SoLanGui,
                error,
            )
            failed_count += 1
        else:
            notification.TrangThai = "Đã gửi"
            notification.ThoiDiemGui = business_now()
            notification.LoiGui = None
            db.commit()
            sent_count += 1

    return {
        "processed": processed_count,
        "sent": sent_count,
        "failed": failed_count,
    }
