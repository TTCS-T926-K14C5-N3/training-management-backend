from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String
)

from app.database import Base


class RevokedToken(Base):
    __tablename__ = "RevokedToken"

    Id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    Jti = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    ExpiresAt = Column(
        DateTime,
        nullable=False
    )

    RevokedAt = Column(
        DateTime,
        nullable=False,
        default=datetime.now
    )