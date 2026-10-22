from app.routers import auth
from app.schemas.login import LoginRequest
from app.schemas.resend_activation import ResendActivationRequest


def test_login_includes_avatar_url(monkeypatch):
    login_response = {
        "nguoiDungId": 42,
        "access_token": "test-token",
    }
    expected_avatar_url = "/users/42/avatar?v=123"
    monkeypatch.setattr(
        auth,
        "login_user",
        lambda _db, _request: login_response,
    )
    monkeypatch.setattr(
        auth,
        "avatar_url_for_user",
        lambda user_id: (
            expected_avatar_url if user_id == 42 else None
        ),
    )

    response = auth.login(
        LoginRequest(email="user@example.com", password="password"),
        db=object(),
    )

    assert response["avatarUrl"] == expected_avatar_url


def test_resend_activation_endpoint_delegates_to_service(monkeypatch):
    expected = {"message": "generic response"}
    request = ResendActivationRequest(email="user@example.com")
    db = object()
    monkeypatch.setattr(
        auth,
        "resend_activation",
        lambda actual_db, actual_request: (
            expected
            if actual_db is db and actual_request is request
            else None
        ),
    )

    assert auth.resend_activation_endpoint(request, db) == expected
