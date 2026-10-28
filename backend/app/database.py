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

# Ensure postgres:// URL scheme is compatible with SQLAlchemy
raw_db_url = settings.DATABASE_URL
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    raw_db_url,
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
