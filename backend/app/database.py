"""Database connection and SQLAlchemy session management for NM-HireX."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
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

def ensure_ist_datetime_columns() -> None:
    """Migrate legacy TIMESTAMPTZ columns on PostgreSQL to naive IST TIMESTAMP once.

    Existing `interview_scheduled_at`, `created_at`, and `updated_at` values stored as UTC
    are converted to Asia/Kolkata wall-clock timestamps; `candidate_contacts` action
    timestamps (already written in naive IST) retain their stored clock digits.
    """
    if engine.dialect.name != "postgresql":
        return

    columns_to_migrate = (
        ("job_candidates", "interview_scheduled_at", "Asia/Kolkata"),
        ("users", "created_at", "Asia/Kolkata"),
        ("users", "updated_at", "Asia/Kolkata"),
        ("jobs", "created_at", "Asia/Kolkata"),
        ("jobs", "updated_at", "Asia/Kolkata"),
        ("candidates", "created_at", "Asia/Kolkata"),
        ("candidates", "updated_at", "Asia/Kolkata"),
        ("job_candidates", "created_at", "Asia/Kolkata"),
        ("job_candidates", "updated_at", "Asia/Kolkata"),
        ("candidate_contacts", "created_at", "Asia/Kolkata"),
        ("candidate_contacts", "sent_at", "UTC"),
        ("candidate_contacts", "delivered_at", "UTC"),
        ("candidate_contacts", "read_at", "UTC"),
        ("candidate_contacts", "responded_at", "UTC"),
    )

    with engine.begin() as conn:
        for table_name, column_name, source_zone in columns_to_migrate:
            data_type = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = :table_name AND column_name = :column_name"
                ),
                {"table_name": table_name, "column_name": column_name},
            ).scalar()
            if data_type == "timestamp with time zone":
                conn.execute(
                    text(
                        f'ALTER TABLE "{table_name}" '
                        f'ALTER COLUMN "{column_name}" TYPE TIMESTAMP WITHOUT TIME ZONE '
                        f"USING ({column_name} AT TIME ZONE '{source_zone}')"
                    )
                )


def get_db() -> Generator[Session, None, None]:
    """Create one DB session per request and close it afterward."""

    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
