"""Database connection and SQLAlchemy session management for NM-HireX."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings


# ------------------------------------------------------------
# DATABASE ENGINE
# ------------------------------------------------------------
# The current NM-HireX project uses PostgreSQL/Neon in production.
# psycopg2-binary is already part of the project's dependencies.
# ------------------------------------------------------------

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)


# ------------------------------------------------------------
# SESSION FACTORY
# ------------------------------------------------------------

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# ------------------------------------------------------------
# FASTAPI DATABASE DEPENDENCY
# ------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """Create one DB session per request and close it afterward."""

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
