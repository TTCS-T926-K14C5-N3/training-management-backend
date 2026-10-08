# Role-based access control

The backend initializes the eight system roles and permission catalog at startup.
On a new database, it applies the explicit defaults in
`app/services/rbac_service.py`. On an existing database it adds missing
permission definitions without replacing configured grants; new permission codes
are assigned only according to the declared defaults. The Quản trị hệ thống role
keeps `ROLE_VIEW` and `ROLE_UPDATE` so an administrator cannot lock out the
management interface.

All protected API handlers must enforce authorization on the server:

```python
@router.put(
    "/resource/{resource_id}",
    dependencies=[Depends(require_permission("RESOURCE_UPDATE"))],
)
def update_resource(...):
    ...
```

`require_permission` checks the current user's role-to-permission links in the
database for each request. A missing permission row or role assignment denies
access with HTTP 403 and a Vietnamese message. Client-side route checks only
control navigation and are not an authorization boundary.

## Academic management

The academic API uses the SQL Server schema in
`migrations/002_academic_management.sql`. Start the backend once so RBAC
initializes its roles and permission catalog, run that migration against the
configured database, then run `migrations/003_training_programs.sql` and
`migrations/004_seed_training_catalog.sql` in order before restarting the
backend. The last migration inserts starter IT programs and subjects only when
their codes do not already exist; it can be rerun without replacing existing
catalog entries.

The academic migrations create subject and program catalogs, classes,
class/student and class/subject assignments, and term-based grades. Class and
subject removal is archival; grades are retained. A student can only read
their own grades, instructors can read and edit grades for classes assigned
to them, and training managers and system administrators have the broader view
granted to their roles. All API handlers enforce server-side permissions, and
the service additionally applies these record-level scopes.
