# Backend EduManage

## Yêu cầu (Windows)

- Python 3.11 trở lên
- Microsoft SQL Server (cài trên máy hoặc có thể kết nối qua mạng)
- Microsoft ODBC Driver 18 for SQL Server

Tạo môi trường ảo và cài các thư viện cần thiết:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Cấu hình SQL Server

Sao chép `.env.example` thành `.env`, sau đó cấu hình `DB_SERVER` và
`DB_NAME`. Nếu SQL Server cài trên cùng máy, thường có thể dùng
`DB_SERVER=localhost`. Nếu SQL Server ở máy khác, hãy nhập tên máy hoặc địa
chỉ IP có thể truy cập được, đồng thời bật TCP/IP và mở cổng tường lửa SQL
Server phù hợp.

Mặc định `DB_TRUSTED_CONNECTION=yes` sử dụng xác thực tích hợp của Windows.
Nếu máy chạy backend không thể xác thực với SQL Server bằng tài khoản Windows
đó (thường gặp khi SQL Server ở máy khác), đặt `DB_TRUSTED_CONNECTION=no` và
cấu hình `DB_USER`, `DB_PASSWORD` cho tài khoản đăng nhập SQL Server. Không
đưa file `.env` thật lên kho mã nguồn hoặc chia sẻ thông tin đăng nhập trong
file này.

Khởi tạo cấu trúc cơ sở dữ liệu bằng `QuanLyDaoTao_database.sql`, sau đó chạy
các tập lệnh migration trong thư mục `migrations/` theo thứ tự số tăng dần nếu
chúng chưa được áp dụng cho cơ sở dữ liệu.

## Chạy API

Chỉ cho phép truy cập từ máy hiện tại:

```powershell
uvicorn app.main:app --reload
```

Để các máy khác trong cùng mạng LAN truy cập backend, chạy lệnh sau trên máy
chủ:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Trong file `.env`, đặt `CORS_ORIGINS` thành danh sách các địa chỉ frontend
được phép truy cập, phân tách bằng dấu phẩy và gồm đúng địa chỉ cùng cổng. Ví
dụ: `http://192.168.1.20:5173`. Đặt `FRONTEND_URL` thành địa chỉ frontend
trong mạng LAN đó để liên kết kích hoạt tài khoản và đặt lại mật khẩu trong
email không trỏ về `localhost` của máy người nhận.

Chỉ mở cổng TCP 8000 trong Windows Firewall cho mạng Private. Từ một máy
khác, kiểm tra backend tại `http://<ip-backend>:8000/api/health`.

Xem README của frontend để biết cách cài đặt và chạy giao diện web.

## Chạy kiểm thử

```powershell
python -m pytest -q
```
