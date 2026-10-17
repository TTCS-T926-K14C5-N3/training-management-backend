import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_xem_truoc_thoi_khoa_bieu_unauthorized():
    # Kiểm tra API xem trước khi chưa truyền thông tin hợp lệ / không có token
    response = client.post("/thoi-khoa-bieu/xem-truoc", json={})
    assert response.status_code in [401, 403, 422]

def test_gan_bai_hoc_not_found():
    # Kiểm tra gắn bài học cho buổi học không tồn tại
    response = client.put(
        "/thoi-khoa-bieu/999999/gan-bai-hoc",
        json={"bai_hoc_id": 1, "noi_dung_bai_hoc": "Bài 1: Tổng quan"}
    )
    assert response.status_code in [401, 403, 404]  
def test_get_lich_hoc_ca_nhan_unauthorized():
    # Kiểm tra API truy vấn lịch học cá nhân khi không truyền Token xác thực
    response = client.get("/thoi-khoa-bieu/ca-nhan")
    assert response.status_code in [401, 403]