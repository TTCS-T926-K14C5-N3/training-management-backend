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
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\005_curriculum_admissions.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\006_curriculum_admissions.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\007_lead_student_conversion.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\008_sprint_3.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\009_seed_sprint3_permissions.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\009_student_profiles.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\010_class_schedules.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\011_require_schedule_room.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\012_student_enrollment_actions.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\013_sprint3_class_enrichment.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\013_session_attendance.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\014_schedule_notifications.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\016_assignments.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\017_attendance.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\017_student_schedule_view.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\018_sprint4_attendance_completion.sql
```

`-f 65001` giúp `sqlcmd` đọc đúng các ký tự tiếng Việt trong tập lệnh UTF-8.
`-E` dùng xác thực Windows. Nếu cấu hình SQL Server dùng tài khoản SQL, thay
`-E` bằng `-U <DB_USER> -P <DB_PASSWORD>` (không ghi mật khẩu vào lịch sử lệnh
hoặc kho mã nguồn).

Hai tập lệnh có tiền tố `013` là các migration riêng biệt và đều cần được áp
dụng; có thể chạy theo thứ tự liệt kê ở trên.

Ứng dụng tự bổ sung các quyền `SCHEDULE_VIEW`, `SCHEDULE_CREATE` và
`SCHEDULE_UPDATE` khi khởi động. Giảng viên/trợ giảng mặc định được xem lịch;
quản lý đào tạo và quản trị viên có quyền tạo, cập nhật và hủy buổi học.
Học viên cũng được xem lịch trong phạm vi các lớp đã ghi danh.
`013_sprint3_class_enrichment.sql` cập nhật loại phòng cho luồng lớp học;
`016_assignments.sql` tạo các bảng bài tập/bài nộp/chấm điểm và quyền bài tập;
`017_attendance.sql` tạo bảng điểm danh, đơn xin vắng, lịch sử, ngưỡng vắng
và thông báo. Chạy các migration này trước khi sử dụng các màn hình tương ứng.
Học viên, giảng viên và trợ giảng mặc định
được xem lịch trong phạm vi lớp được phép truy cập; quản lý đào tạo và quản trị
viên có quyền tạo, cập nhật và hủy buổi học. Chạy migration
`017_student_schedule_view.sql` để cấp quyền xem lịch cho vai trò học viên trên
cơ sở dữ liệu hiện có. Migration `018_sprint4_attendance_completion.sql` bổ sung
liên kết buổi học với lịch, đơn xin phép vắng, nhật ký/thông báo điểm danh và
chuẩn hóa trạng thái điểm danh.

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
  `assigned_user_id`, `start_date`, `end_date`, `search`. Khi tạo/cập nhật lead,
  `chuongTrinhId` có thể để trống nếu chưa xác định chương trình; chạy lại
  migration `005_curriculum_admissions.sql` để cập nhật cột trên cơ sở dữ liệu cũ.
  `PUT /admissions/leads/{lead_id}/assignments` nhận
  `{ "consultantIds": [5] }` để giao một tư vấn viên hoặc `[]` để gỡ phân công.
  `PUT /admissions/leads/bulk-assignments` nhận danh sách lead và một tư vấn viên
  dùng chung cho các lead đã chọn; `consultantIds: []` gỡ phân công hàng loạt.
  Lịch sử giao/gỡ được trả trong `lichSuBanGiao`. `GET /admissions/consultants`
  liệt kê tư vấn viên đang hoạt động. `POST
  /admissions/leads/{lead_id}/convert-to-student` tạo tài khoản học viên từ
  thông tin lead, gán vai trò học viên, sinh mã `HV` theo ID người dùng và gửi
  email kích hoạt; yêu cầu lead có email chưa được sử dụng. Lead đã nhập học
  không thể sửa hoặc xóa. Áp dụng `migrations/007_lead_student_conversion.sql`
  sau các migration tuyển sinh để đồng bộ độ dài email tài khoản, tạo bảng liên
  kết chuyển đổi và cho phép trạng thái `Đã nhập học`.
- Sprint 3 bổ sung luồng trạng thái lead `Mới → Đã liên hệ → Đang tư vấn → Hẹn
  học thử → Chốt`, kết thúc với `Từ chối` hoặc chuyển đổi thành `Đã nhập học`.
  Mỗi lần đổi trạng thái được lưu lịch sử; từ chối bắt buộc có lý do.
  `POST/GET /admissions/leads/{lead_id}/interactions` ghi nhật ký gọi, nhắn tin,
  gặp và lịch gọi lại; phản hồi lead đánh dấu cuộc gọi quá hạn để giao diện làm
  nổi bật.
- Sau migration `008_sprint_3.sql`, lớp có ngày khai giảng, sĩ số tối đa,
  hình thức học, phòng/link trực tuyến, trạng thái vòng đời và tiến độ. API
  `/academic/rooms` quản lý phòng; `POST /academic/classes/{class_id}/enrollments`
  ghi danh hàng loạt, từ chối ghi danh vượt sĩ số lớp và trả về học viên đã có
  trong lớp thay vì tạo trùng. Sức chứa phòng vượt ngưỡng là cảnh báo, không
  chặn ghi danh.
- `GET /academic/classes` hỗ trợ lọc `status`, `programId`, `instructorId`,
  `startDate`, `endDate`. `GET /academic/students/{student_id}` trả hồ sơ học
  viên cùng lịch sử lớp và điểm, giới hạn theo quyền lớp/giảng viên/học viên.
  `GET /academic/students/statuses` hỗ trợ `hasHistory=true` để chỉ lấy học viên
  có lớp được bảo lưu, chuyển lớp, thôi học hoặc đã kết thúc; có thể kết hợp
  `search`, `status`, `classId`, `enrollmentStatus` và phân trang.
  Mỗi môn lớp có một giảng viên chính và có thể có nhiều trợ giảng; danh sách
  phân công sử dụng cả vai trò giảng viên và trợ giảng.
- Lịch buổi học:
  - `GET /academic/schedule-options` lấy lớp/môn trong phạm vi truy cập cùng
    danh sách giảng viên và phòng đang hoạt động.
  - `GET /academic/schedules` liệt kê lịch; hỗ trợ `startDate`, `endDate`,
    `status` và `excludeCompleted=true` để ẩn buổi đã kết thúc khỏi danh sách
    lịch hiện hành.
  - `GET /academic/schedules/completed` trả lịch sử buổi đã diễn ra theo lớp
    người dùng được quyền xem; hỗ trợ phân trang `page`, `pageSize` và phản hồi
    `items`, `total`, `page`, `pageSize`.
  - `POST /academic/schedules` nhận `lopHocId`, `monHocId`, `ngayHoc`,
    `gioBatDau`, `gioKetThuc`, `phongHocId`, `giangVienId` và `baiHocId`
    tùy chọn để gắn buổi học trong chương trình.
  - `POST /academic/schedules/preview` xem trước lịch lặp;
    `POST /academic/schedules/bulk` tạo các buổi đã xem trước. Request nhận
    `ngayBatDau`, `soBuoi`, `thuTrongTuan`, `ngayNghi` cùng lớp/môn, phòng,
    giảng viên và giờ học; bài học được gắn theo thứ tự chương trình.
  - `POST /academic/schedules/generate-preview` và
    `POST /academic/schedules/generate` xem trước và tạo hàng loạt lịch theo
    tuần, bỏ qua ngày nghỉ và kiểm tra xung đột trước khi lưu.
  - `PUT /academic/schedules/{schedule_id}` cập nhật ngày, giờ, phòng và
    giảng viên; lớp/môn là thông tin cố định.
  - `POST /academic/schedules/{schedule_id}/cancel` nhận `{ "lyDo": "..." }`;
    lý do bắt buộc, lịch đã bắt đầu/đã qua giờ không thể sửa hoặc hủy.
  - Ngày/giờ của lịch được truyền dưới dạng ngày và giờ địa phương, không kèm
    offset múi giờ; SQL Server lưu `DATE`, `TIME` và `DATETIME2` theo giờ nghiệp
    vụ `Asia/Ho_Chi_Minh`. Ngày quá khứ, khung giờ kết thúc hoặc bắt đầu đã qua
    trong ngày hiện tại và giờ kết thúc không sau giờ bắt đầu đều bị từ chối ở
    API, độc lập với kiểm tra trên giao diện.
  - `GET /academic/schedule-history` nhận `page`, `pageSize` (tối đa 100),
    `q` và `eventType` (`all`, `date_time`, `room`, `instructor`, `cancelled`).
    Tìm kiếm thực hiện phía Backend trên mã buổi, lớp, người thực hiện, nội
    dung thông báo, lý do và ảnh chụp thay đổi; phản hồi có `items`, `total`,
    `page` và `pageSize`. Sự kiện gồm ảnh chụp trước/sau, người thực hiện,
    thời điểm và tổng trạng thái gửi thông báo nếu có.
    Xung đột lịch trả HTTP 409 cùng `detail.conflicts` chứa loại tài nguyên,
    tên, ngày/giờ và buổi học/lớp đang trùng. Chỉ người có quyền
    `SCHEDULE_OVERRIDE` mới có thể gửi `ghiDeXungDot: true`; mọi lần ghi đè phải
    lưu `lyDoGhiDe` và được ghi vào lịch sử thay đổi.
  - Khi lịch đổi hoặc bị hủy, hệ thống lưu thông báo email theo từng học viên
    đang ghi danh và giảng viên liên quan, kèm dữ liệu trước/sau. Trạng thái
    gửi, số lần thử và lỗi được lưu bền vững; SMTP dùng cấu hình trong `.env`.
    `POST /academic/schedule-notifications/retry` (quyền `SCHEDULE_UPDATE`)
    thử lại thông báo đang chờ/thất bại tối đa ba lần gửi tổng cộng mỗi bản ghi,
    tối đa 100 bản ghi mỗi lần gọi. Bản ghi chờ gửi được xử lý lại khi ứng dụng
    khởi động. Migration `014_schedule_notifications.sql` chỉ thêm bảng; nếu
    cần rollback, sao lưu lịch sử trước rồi chỉ xóa bảng sau khi đã dừng ứng
    dụng và được phê duyệt vì thao tác đó sẽ xóa dữ liệu thông báo.
  - `GET/PUT /academic/schedules/{schedule_id}/attendance` xem và cập nhật điểm
    danh cho một buổi học, với trạng thái `Có mặt`, `Đi muộn`, `Vắng có phép`
    hoặc `Vắng không phép`. Chỉ được ghi điểm danh khi buổi đã bắt đầu; chỉ
    quản lý đào tạo/quản trị viên được sửa sau khi buổi kết thúc. Mọi thay đổi
    được lưu trong nhật ký tại `GET /academic/schedules/{schedule_id}/attendance/audit`
    (tối đa 360 ngày).
  - Học viên gửi đơn xin phép cho buổi học tại
    `POST /attendance/sessions/absence-requests` hoặc
    `/attendance/sessions/absence-requests/with-evidence` (multipart, PDF/PNG/JPEG
    tối đa 5 MB); người phụ trách lớp duyệt/từ chối tại
    `POST /attendance/sessions/absence-requests/{request_id}/decision`. Đơn được
    duyệt tự động ghi `Vắng có phép`; quyết định gửi thông báo riêng cho học viên.
    `GET /attendance/sessions/absence-requests`,
    `/attendance/sessions/my-history` và
    `/attendance/sessions/notifications` cung cấp dữ liệu theo quyền người dùng.
    Điểm danh theo lớp/ngày và đơn xin vắng theo lớp tiếp tục dùng các endpoint
    `/attendance/classes/...` và `/attendance/absence-requests`.
  - Điểm danh và các bảng xin phép vắng/audit/thông báo cần migration
    `013_session_attendance.sql`, `017_attendance.sql` và
    `018_sprint4_attendance_completion.sql`. `017_attendance.sql` lưu điểm danh
    theo lớp/ngày trong bảng `DiemDanhTheoNgay`; `DiemDanh` vẫn dành riêng cho
    điểm danh theo buổi.
    Lịch đã có bản ghi điểm danh không thể sửa hoặc hủy.
- Bài tập:
  - `GET /assignments/options` lấy lớp, môn và buổi học mà người dùng được phép
    sử dụng; `GET /assignments/mine` và `/assignments/teacher` liệt kê bài tập
    theo vai trò học viên hoặc giảng viên.
  - `POST /assignments` tạo bài tập; `POST /assignments/{assignment_id}/publish`
    phát hành bài tập. Học viên nộp bài tại
    `POST /assignments/{assignment_id}/submissions`; giảng viên xem danh sách
    nộp tại `GET /assignments/{assignment_id}/roster`, chấm bài tại
    `POST /assignments/submissions/{submission_id}/grade` và có thể mở lại bài
    đã chấm tại `POST /assignments/{assignment_id}/students/{student_id}/reopen`.
  - Tệp đính kèm được tải qua
    `GET /assignments/attachments/{kind}/{attachment_id}`. Quyền `ASSIGNMENT_*`
    được khởi tạo cùng catalog RBAC; học viên được xem/nộp, giảng viên/trợ giảng
    được quản lý/chấm bài.
  - Migration `016_assignments.sql` tạo các bảng bài tập, tệp đính kèm, bài nộp
    điểm và lịch sử mở lại.

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
