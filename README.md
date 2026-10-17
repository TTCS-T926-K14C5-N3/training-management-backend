# EduManage schedule management

## Database migrations

After applying the base schema and migrations `001`–`005`, and allowing the
application to initialize its role and permission catalog, apply these
migrations in order from the backend repository root:

```powershell
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\010_class_schedules.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\011_require_schedule_room.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\012_student_enrollment_actions.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\013_session_attendance.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\014_schedule_notifications.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\015_class_subject_instructors.sql
sqlcmd -f 65001 -S <DB_SERVER> -d <DB_NAME> -E -b -i migrations\016_schedule_class_fields.sql
```

`-f 65001` preserves Vietnamese text in UTF-8 scripts. Use the database's
approved SQL Server authentication method in place of `-E` when Windows
integrated authentication is unavailable. These migrations reuse the existing
class, subject, room, user, and enrollment tables.

## Schedule APIs

All endpoints below require the corresponding schedule or attendance
permission:

- `GET /academic/schedules` lists accessible sessions.
- `POST /academic/schedules` creates a session.
- `PUT /academic/schedules/{schedule_id}` updates a session.
- `POST /academic/schedules/{schedule_id}/cancel` cancels a session.
- `GET /academic/schedule-history` returns paginated history. It accepts
  `page`, `pageSize`, `q`, and `eventType` (`all`, `date_time`, `room`,
  `instructor`, or `cancelled`).
- `GET /academic/schedules/{schedule_id}/attendance` and
  `PUT /academic/schedules/{schedule_id}/attendance` manage attendance.

Schedule changes and their audit entries are committed together. Notification
delivery status is reported separately and retained for retry; an email
failure does not roll back a successfully saved schedule.

## Date and time convention

Business time is `Asia/Ho_Chi_Minh`. Schedule dates and times are stored as
SQL `DATE`/`TIME` values, while legacy SQL `DATETIME` columns contain naive
Vietnam local wall time. Requests must use local times without UTC offsets.
Both the API and the frontend reject past dates, expired same-day sessions,
and end times that are not after start times.

## Tests

Run the backend suite from this directory:

```powershell
python -m pytest -q
```
