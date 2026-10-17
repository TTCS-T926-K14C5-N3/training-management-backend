from fastapi import FastAPI
from app.database import SessionLocal
from app.services.rbac_service import initialize_role_permissions
from app.services.schedule_notifications import process_schedule_notifications

from fastapi.middleware.cors import CORSMiddleware

from app.routers.health import (
    router as health_router
)

from app.routers.auth import (
    router as auth_router
)

from app.routers.vai_tro import (
    router as vai_tro_router
)

from app.routers.nguoi_dung import (
    router as nguoi_dung_router
)
from app.routers.academic import (
    router as academic_router
)
from app.routers.thoi_khoa_bieu import (
    router as thoi_khoa_bieu_router
)
from app.routers.schedules import (
    router as schedules_router
)


app = FastAPI(
    title="Quan ly dao tao",
    version="1.0.0"
)


@app.on_event("startup")
def initialize_rbac():
    db = SessionLocal()
    try:
        initialize_role_permissions(db)
        while True:
            result = process_schedule_notifications(db, limit=100)
            if result["processed"] < 100:
                break
    finally:
        db.close()


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# ============================================================
# ROUTERS
# ============================================================

app.include_router(
    health_router
)

app.include_router(
    auth_router
)

app.include_router(
    vai_tro_router
)

app.include_router(
    nguoi_dung_router
)

app.include_router(
    academic_router
)

app.include_router(
    thoi_khoa_bieu_router
)

app.include_router(
    schedules_router
)
