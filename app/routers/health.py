from fastapi import APIRouter
from app.database import engine

router = APIRouter(tags=["Health"])


@router.get("/")
def home():
    return {"message": "Backend dang hoat dong"}


@router.get("/test-db")
def test_db():
    try:
        with engine.connect():
            return {"message": "Ket noi SQL Server thanh cong"}
    except Exception as e:
        return {
            "message": "Ket noi SQL Server that bai",
            "error": str(e)
        }


@router.get("/api/health")
@router.get("/health")
def health():
    return {
        "status": "ok",
        "message": "Frontend da ket noi Backend thanh cong"
    }