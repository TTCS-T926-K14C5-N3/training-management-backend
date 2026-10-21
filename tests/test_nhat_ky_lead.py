import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_leads_qua_han_goi_lai_unauthorized():
    # Kiểm tra API khi không gửi token phân quyền
    response = client.get("/leads/qua-han-goi-lai")
    assert response.status_code in [401, 403]

def test_create_nhat_ky_lead_not_found():
    # Kiểm tra ghi nhật ký cho Lead không tồn tại (LeadId = 999999)
    response = client.post(
        "/leads/999999/nhat-ky",
        json={
            "phuong_thuc": "GoiDien",
            "noi_dung": "Test nhat ky cham soc",
            "ket_qua": "Thanh cong"
        }
    )
    assert response.status_code in [401, 403, 404]