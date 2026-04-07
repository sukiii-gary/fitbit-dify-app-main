from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db import base  # noqa: F401
from app.models.base import Base

settings = get_settings()

engine = create_engine(
    settings.resolved_database_url,
    connect_args={"check_same_thread": False} if settings.resolved_database_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)


def create_db_and_tables() -> None:
    Base.metadata.create_all(bind=engine)
