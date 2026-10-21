from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS
from app.database import SessionLocal
from app.services.rbac_service import initialize_role_permissions
from app.routers.academic import router as academic_router
from app.routers.admissions import router as admissions_router
from app.routers.assignments import router as assignments_router
from app.routers.attendance import router as attendance_router
from app.routers.attendance_sessions import (
    audit_router as session_attendance_audit_router,
    router as session_attendance_router,
)
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.routers.nguoi_dung import router as nguoi_dung_router
from app.routers.schedules import router as schedules_router
from app.routers.thoi_khoa_bieu import router as thoi_khoa_bieu_router
from app.routers.vai_tro import router as vai_tro_router


app = FastAPI(
    title="Quan ly dao tao",
    version="1.0.0",
)


@app.on_event("startup")
def initialize_rbac():
    db = SessionLocal()
    try:
        initialize_role_permissions(db)
    finally:
        db.close()


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(vai_tro_router)
app.include_router(nguoi_dung_router)
app.include_router(academic_router)
app.include_router(admissions_router)
app.include_router(thoi_khoa_bieu_router)
app.include_router(schedules_router)
app.include_router(assignments_router)
app.include_router(attendance_router)
app.include_router(session_attendance_router)
app.include_router(session_attendance_audit_router)
