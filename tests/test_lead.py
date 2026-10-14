import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_lead_list_unauthorized():
    # Kiểm tra truy cập danh sách Lead khi không truyền Token/Permission -> Phải bị từ chối (401/403)
    response = client.get("/leads/")
    assert response.status_code in [401, 403]

def test_create_lead_unauthorized():
    # Kiểm tra tạo Lead khi không có quyền LEAD_CREATE -> Phải bị từ chối
    response = client.post(
        "/leads/",
        json={
            "ho_ten": "Test Lead",
            "so_dien_thoai": "0912345678"
        }
    )
    assert response.status_code in [401, 403]