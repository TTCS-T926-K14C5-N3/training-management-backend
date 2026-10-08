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

## Danh mục đào tạo và tuyển sinh

Sau khi đã áp dụng các migration `002` và `003` và ứng dụng đã khởi tạo các vai
trò hệ thống 1–8, áp dụng migration tính năng (có thể chạy lại an toàn) từ thư
mục gốc trên Windows:

```powershell
sqlcmd -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\005_curriculum_admissions.sql
sqlcmd -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\006_curriculum_admissions.sql
```

`-E` dùng xác thực Windows. Nếu cấu hình SQL Server dùng tài khoản SQL, thay
`-E` bằng `-U <DB_USER> -P <DB_PASSWORD>` (không ghi mật khẩu vào lịch sử lệnh
hoặc kho mã nguồn).

Các hợp đồng API chính (các trường JSON dùng camelCase):

- `GET/POST /academic/subjects`, `PUT/DELETE /academic/subjects/{subject_id}`:
  quản lý môn học gồm `maMonHoc`, `tenMonHoc`, `soBuoi`, `trongSo`,
  `moTaChuanDauRa`, `trangThai`. `trongSo` là hệ số decimal trong khoảng
  `[0, 1]`. `DELETE` lưu trữ thay vì xóa cứng.
- `GET/PUT /academic/programs/{program_id}/subjects`: PUT nhận
  `{ "subjects": [{ "monHocId": 1, "thuTu": 1, "monTienQuyetId": null }] }`.
  GET trả về các môn theo thứ tự, kèm các `sessions`.
- `GET/PUT /academic/programs/{program_id}/subjects/{subject_id}/sessions`:
  PUT nhận `{ "sessions": [{ "soThuTu": 1, "chuDe": "...", "mucTieu": "..." }] }`.
- `GET /admissions/program-options` và
  `POST /admissions/public/leads` là endpoint công khai. Honeypot nhận trường
  `website`; phản hồi xác nhận thời gian liên hệ trong một ngày làm việc.
- `/admissions/leads` hỗ trợ CRUD và bộ lọc `status`, `source`,
  `assigned_user_id`, `start_date`, `end_date`, `search`.
  `PUT /admissions/leads/{lead_id}/assignments` nhận
  `{ "consultantIds": [5, 6] }`; lịch sử bàn giao được trả trong `lichSuBanGiao`.
  `GET /admissions/consultants` liệt kê tư vấn viên đang hoạt động.

Các endpoint danh mục dùng quyền `CURRICULUM_VIEW/CREATE/UPDATE/DELETE`.
Quyền `LEAD_VIEW/CREATE/UPDATE` được cấp cho tuyển sinh; `LEAD_DELETE` và
`LEAD_ASSIGN` chỉ dành cho quản lý đào tạo/quản trị viên. Tư vấn viên tuyển sinh
chỉ xem lead đang được phân công cho mình.

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
