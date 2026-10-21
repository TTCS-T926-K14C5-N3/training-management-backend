import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_lich_su_diem_danh_unauthorized():
    # Kiểm tra API khi chưa truyền Token đăng nhập
    response = client.get("/diem-danh/ca-nhan")
    assert response.status_code in [401, 403]