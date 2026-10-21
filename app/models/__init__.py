from app.models.absence_request import (
    AbsenceRequest,
    AttendanceAudit,
    AttendanceNotification,
)
from app.models.admissions import Lead, LeadAssignmentHistory, LeadConversion
from app.models.assignment import (
    Assignment,
    AssignmentAttachment,
    AssignmentGrade,
    AssignmentReopen,
    AssignmentSubmission,
    AssignmentSubmissionAttachment,
)
from app.models.chuong_trinh_dao_tao import ChuongTrinhDaoTao
from app.models.diem_danh import DiemDanh
from app.models.lead_activity import LeadInteraction, LeadStatusHistory
from app.models.lich_hoc import LichHoc, LichHocLichSu
from app.models.lop_hoc import LopHoc
from app.models.lop_hoc_hoc_vien import LopHocHocVien
from app.models.lop_hoc_mon_hoc import LopHocMonHoc
from app.models.lop_hoc_mon_hoc_giang_vien import LopHocMonHocGiangVien
from app.models.mon_hoc import MonHoc
from app.models.nguoi_dung import NguoiDung
from app.models.nguoi_dung_vai_tro import NguoiDungVaiTro
from app.models.phong_hoc import PhongHoc
from app.models.quyen import Quyen
from app.models.revoked_token import RevokedToken
from app.models.thoi_khoa_bieu import (
    ThoiKhoaBieu,
    ThoiKhoaBieuDiemDanh,
    ThoiKhoaBieuLichSu,
)
from app.models.token_mat_khau import TokenMatKhau
from app.models.vai_tro import VaiTro
from app.models.vai_tro_quyen import VaiTroQuyen
