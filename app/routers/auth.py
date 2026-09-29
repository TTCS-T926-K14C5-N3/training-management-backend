from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.login import LoginRequest
from app.services.auth_service import login_user


router = APIRouter(tags=["Authentication"])


@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    return login_user(db, request)