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
    })
    assert assignment.tieu_de == "Bài thực hành"
    assert assignment.mo_ta.startswith("Hoàn thiện")
    assert assignment.diem_toi_da == Decimal("25.50")
    assert assignment.cho_nop_muon is True
    assert assignment.han_nop.tzinfo is not None


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
