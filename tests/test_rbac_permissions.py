from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.security import require_permission
from app.models.vai_tro_quyen import VaiTroQuyen
from app.services.rbac_service import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSION_CATALOG,
)


class FakePermissionResult:
    def __init__(self, allowed: bool):
        self.allowed = allowed

    def first(self):
        return object() if self.allowed else None


class FakePermissionDatabase:
    def __init__(self, role_id: int, role_name: str = ""):
        self.role_id = role_id
        self.role_name = role_name

    def execute(self, query, parameters):
        granted_codes = set(DEFAULT_ROLE_PERMISSIONS.get(self.role_id, ()))
        sql = str(query).lower()
        is_admin_clause = (
            (self.role_id == 8 and "vaitroid = 8" in sql)
            or (
                self.role_name.strip().casefold()
                in {
                    "admin",
                    "quản trị hệ thống",
                    "quản trị viên hệ thống",
                }
                and "quản trị viên hệ thống" in sql
            )
        )
        return FakePermissionResult(
            is_admin_clause or parameters["ma_quyen"] in granted_codes
        )


@pytest.mark.parametrize(
    ("role_id", "permission_code"),
    [
        (3, "GRADE_UPDATE"),
        (6, "TUITION_UPDATE"),
        (8, "ROLE_UPDATE"),
    ],
)
def test_expected_role_permissions_are_allowed(role_id, permission_code):
    check_permission = require_permission(permission_code)

    user = SimpleNamespace(NguoiDungId=role_id)
    result = check_permission(
        current_user=user,
        db=FakePermissionDatabase(role_id),
    )

    assert result is user


def test_admin_role_is_allowed_even_when_permission_is_not_seeded():
    check_permission = require_permission("PERMISSION_MISSING_FROM_DATABASE")
    user = SimpleNamespace(NguoiDungId=8)

    result = check_permission(
        current_user=user,
        db=FakePermissionDatabase(8),
    )

    assert result is user


def test_admin_name_is_allowed_when_role_id_is_not_eight():
    check_permission = require_permission("PERMISSION_MISSING_FROM_DATABASE")
    user = SimpleNamespace(NguoiDungId=99)

    result = check_permission(
        current_user=user,
        db=FakePermissionDatabase(99, "Quản trị hệ thống"),
    )

    assert result is user


@pytest.mark.parametrize(
    ("role_id", "permission_code"),
    [
        (3, "TUITION_UPDATE"),
        (6, "GRADE_UPDATE"),
        (4, "GRADE_VIEW"),
        (2, "USER_DELETE"),
    ],
)
def test_missing_role_permissions_are_denied(role_id, permission_code):
    check_permission = require_permission(permission_code)

    with pytest.raises(HTTPException) as error:
        check_permission(
            current_user=SimpleNamespace(NguoiDungId=role_id),
            db=FakePermissionDatabase(role_id),
        )

    assert error.value.status_code == 403
    assert "Bạn không có quyền" in error.value.detail


def test_catalog_contains_all_eight_business_role_defaults():
    codes = {code for code, _name, _description in PERMISSION_CATALOG}

    assert set(DEFAULT_ROLE_PERMISSIONS) == set(range(1, 9))
    assert "GRADE_UPDATE" in codes
    assert "TUITION_UPDATE" in codes
    assert "TUITION_UPDATE" not in DEFAULT_ROLE_PERMISSIONS[3]
    assert "GRADE_UPDATE" not in DEFAULT_ROLE_PERMISSIONS[6]
    assert "GRADE_VIEW" not in DEFAULT_ROLE_PERMISSIONS[4]
    assert {
        "GRADE_VIEW",
        "GRADE_CREATE",
        "GRADE_UPDATE",
        "QUAN_LY_DIEM",
        "CLASS_VIEW",
    } <= set(DEFAULT_ROLE_PERMISSIONS[3])
    assert {
        "CLASS_VIEW",
        "CLASS_CREATE",
        "CLASS_UPDATE",
        "CLASS_DELETE",
        "QUAN_LY_LOP",
    } <= set(DEFAULT_ROLE_PERMISSIONS[7])


def test_role_permission_model_uses_existing_composite_primary_key():
    primary_key_columns = {
        column.name
        for column in VaiTroQuyen.__table__.primary_key.columns
    }

    assert primary_key_columns == {"VaiTroId", "QuyenId"}
    assert "VaiTroQuyenId" not in VaiTroQuyen.__table__.columns
