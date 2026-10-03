from fastapi import FastAPI

from fastapi.middleware.cors import (
    CORSMiddleware
)

from app.routers.health import (
    router as health_router
)

from app.routers.auth import (
    router as auth_router
)
from app.routers.vai_tro import (
    router as vai_tro_router
)

app = FastAPI(
    title="Quan ly dao tao",
    version="1.0.0"
)


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
from app.routers.nguoi_dung import (
    router as nguoi_dung_router
)

app.include_router(
    nguoi_dung_router
)