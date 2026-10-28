"""PostgreSQL SQLAlchemy models for NM-HireX WhatsApp Outreach & Recruitment.

Only the necessary tables for WhatsApp outreach, candidate management,
and interview scheduling are defined and registered on Base.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ============================================================
# 1. USERS (Authentication & Role Management)
# ============================================================
class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(30), default="RECRUITER", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="PENDING", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ============================================================
# 2. JOBS (Role / Position container)
# ============================================================
class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(255))
    work_mode: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(50), default="ACTIVE", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ============================================================
# 3. CANDIDATES (Candidate Profiles)
# ============================================================
class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50), index=True)
    location: Mapped[str | None] = mapped_column(String(255))
    total_experience_years: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2)
    )
    current_company: Mapped[str | None] = mapped_column(String(255))
    current_role: Mapped[str | None] = mapped_column(String(255))
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    profile_summary: Mapped[str | None] = mapped_column(Text)
    raw_profile_text: Mapped[str | None] = mapped_column(Text)
    normalized_profile: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ============================================================
# 4. JOB_CANDIDATES (Recruitment Workflow, Status & Scheduling)
# ============================================================
class JobCandidate(Base):
    __tablename__ = "job_candidates"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    eligibility_status: Mapped[str] = mapped_column(
        String(50), default="PENDING"
    )
    recruitment_status: Mapped[str] = mapped_column(
        String(50), default="NEW", index=True
    )
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    classification: Mapped[str | None] = mapped_column(String(50))
    is_shortlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    ranking_position: Mapped[int | None] = mapped_column(Integer)
    interview_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    interview_link: Mapped[str | None] = mapped_column(Text)
    reschedule_token: Mapped[str | None] = mapped_column(String(36), unique=True, index=True)
    reminder_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_1h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "candidate_id",
            name="uq_job_candidate",
        ),
    )


# ============================================================
# 5. CANDIDATE_CONTACTS (Outreach & WhatsApp Interaction Log)
# ============================================================
class CandidateContact(Base):
    __tablename__ = "candidate_contacts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    job_candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str | None] = mapped_column(String(50))
    message_type: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(100))
    external_message_id: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str | None] = mapped_column(String(50))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_text: Mapped[str | None] = mapped_column(Text)
    response_intent: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


# ============================================================
# LEGACY COMPATIBILITY STUBS (NOT registered as DB tables)
# These classes do NOT inherit from Base and are NOT created in PostgreSQL.
# ============================================================
class _UnusedLegacyTable:
    pass

JobRequirement = _UnusedLegacyTable
JobSource = _UnusedLegacyTable
Resume = _UnusedLegacyTable
CandidateSource = _UnusedLegacyTable
SkillTaxonomy = _UnusedLegacyTable
CandidateSkill = _UnusedLegacyTable
CandidateExperience = _UnusedLegacyTable
CandidateEducation = _UnusedLegacyTable
CandidateCertification = _UnusedLegacyTable
CandidateProject = _UnusedLegacyTable
ScreeningResult = _UnusedLegacyTable
ScreeningRun = _UnusedLegacyTable
CandidateStatusHistory = _UnusedLegacyTable
CandidateAssessment = _UnusedLegacyTable
IntegrationEvent = _UnusedLegacyTable
AIExtractionLog = _UnusedLegacyTable
