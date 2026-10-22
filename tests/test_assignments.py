from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.assignment import AssignmentWrite, RepositoryUrl
from app.services.assignment_service import MAX_UPLOAD_BYTES, ensure_upload_size


def test_assignment_write_accepts_linked_lesson_and_late_policy():
    assignment = AssignmentWrite.model_validate({
        "lopHocId": 4,
        "monHocId": 8,
        "lichHocId": 12,
        "tieuDe": "  Bài thực hành  ",
        "moTa": "  Hoàn thiện API và gửi liên kết repository.  ",
        "hanNop": "2027-01-10T16:00:00+07:00",
        "diemToiDa": "25.50",
        "choNopMuon": True,
        "hanNopMuon": "2027-01-15T16:00:00+07:00",
        "loaiPhatNopMuon": "percentage_per_day",
        "giaTriPhat": "5.00",
        "diemSanToiThieu": "10.00",
    })
    assert assignment.tieu_de == "Bài thực hành"
    assert assignment.mo_ta.startswith("Hoàn thiện")
    assert assignment.diem_toi_da == Decimal("25.50")
    assert assignment.cho_nop_muon is True
    assert assignment.han_nop.tzinfo is not None
    assert assignment.han_nop_muon.tzinfo is not None
    assert assignment.loai_phat_nop_muon == "percentage_per_day"
    assert assignment.gia_tri_phat == Decimal("5.00")
    assert assignment.diem_san_toi_thieu == Decimal("10.00")


@pytest.mark.parametrize("url", [
    "http://github.com/user/repo",
    "https://github.com",
    "https://user:secret@example.com/repo",
    "javascript:alert(1)",
    "https://example.com/",
])
def test_repository_url_rejects_invalid_or_non_repository_urls(url: str):
    with pytest.raises(ValidationError):
        RepositoryUrl(url=url)


def test_repository_url_accepts_https_path():
    assert RepositoryUrl(url=" https://git.example.org/team/project.git ").url == "https://git.example.org/team/project.git"


def test_assignment_rejects_blank_description_and_nonpositive_points():
    base = {
        "lopHocId": 1,
        "monHocId": 2,
        "lichHocId": 3,
        "tieuDe": "Test",
        "moTa": "Description",
        "hanNop": datetime(2027, 1, 1),
        "diemToiDa": 10,
    }
    with pytest.raises(ValidationError):
        AssignmentWrite.model_validate({**base, "moTa": "   "})
    with pytest.raises(ValidationError):
        AssignmentWrite.model_validate({**base, "diemToiDa": 0})


def test_upload_size_limit_accepts_exactly_twenty_mebibytes():
    assert MAX_UPLOAD_BYTES == 20 * 1024 * 1024
    ensure_upload_size(MAX_UPLOAD_BYTES)


def test_upload_size_limit_rejects_over_twenty_mebibytes():
    with pytest.raises(HTTPException) as error:
        ensure_upload_size(MAX_UPLOAD_BYTES + 1)
    assert error.value.status_code == 413


def test_assignment_write_rejects_invalid_penalty_type():
    base = {
        "lopHocId": 1,
        "monHocId": 2,
        "lichHocId": 3,
        "tieuDe": "Test",
        "moTa": "Description",
        "hanNop": datetime(2027, 1, 1),
        "diemToiDa": 10,
        "choNopMuon": True,
        "loaiPhatNopMuon": "invalid_type",
    }
    with pytest.raises(ValidationError):
        AssignmentWrite.model_validate(base)


def test_calculate_late_penalty_percentage_per_day():
    from app.services.assignment_service import calculate_late_penalty

    due_date = datetime(2027, 1, 1, 12, 0, 0)
    # Submitted 1.5 days late -> 2 days late
    submitted_at = datetime(2027, 1, 3, 0, 0, 0)

    deduction, final = calculate_late_penalty(
        submitted_at=submitted_at,
        due_date=due_date,
        max_score=Decimal("10.00"),
        raw_score=Decimal("9.00"),
        penalty_type="percentage_per_day",
        penalty_value=Decimal("10.00"),  # 10% of 10 = 1 pt/day * 2 days = 2 pts
        min_score=Decimal("0.00"),
    )
    assert deduction == Decimal("2.00")
    assert final == Decimal("7.00")


def test_calculate_late_penalty_respects_minimum_floor_score():
    from app.services.assignment_service import calculate_late_penalty

    due_date = datetime(2027, 1, 1, 12, 0, 0)
    submitted_at = datetime(2027, 1, 10, 12, 0, 0)  # 9 days late

    deduction, final = calculate_late_penalty(
        submitted_at=submitted_at,
        due_date=due_date,
        max_score=Decimal("100.00"),
        raw_score=Decimal("80.00"),
        penalty_type="fixed_percentage",
        penalty_value=Decimal("50.00"),  # 50% = 50 pts deduction -> 80 - 50 = 30 pts
        min_score=Decimal("40.00"),  # but min score floor is 40!
    )
    assert final == Decimal("40.00")
    assert deduction == Decimal("40.00")  # raw 80 - final 40 = 40 deduction


def test_late_policy_config_write_validates_input():
    from app.schemas.assignment import LatePolicyConfigWrite

    valid = LatePolicyConfigWrite.model_validate({
        "choNopMuon": True,
        "hanNopMuon": "2027-02-01T23:59:00",
        "loaiPhatNopMuon": "percentage_per_day",
        "giaTriPhat": "5.00",
        "diemSanToiThieu": "20.00",
    })
    assert valid.cho_nop_muon is True
    assert valid.loai_phat_nop_muon == "percentage_per_day"
    assert valid.gia_tri_phat == Decimal("5.00")
    assert valid.diem_san_toi_thieu == Decimal("20.00")

    with pytest.raises(ValidationError):
        LatePolicyConfigWrite.model_validate({
            "choNopMuon": True,
            "loaiPhatNopMuon": "not_allowed",
        })


def test_late_policy_api_routes_registered():
    from app.main import app
    from app.routers.assignments import router as assignments_router

    paths = {route.path for route in assignments_router.routes}
    assert "/assignments/{assignment_id}/late-policy" in paths

    app_paths = app.openapi()["paths"]
    assert "/assignments/{assignment_id}/late-policy" in app_paths
    assert "get" in app_paths["/assignments/{assignment_id}/late-policy"]
    assert "put" in app_paths["/assignments/{assignment_id}/late-policy"]

