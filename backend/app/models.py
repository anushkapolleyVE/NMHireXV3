"""PostgreSQL SQLAlchemy Models for NM-HireX WhatsApp Outreach & Recruitment.

This module defines the relational database schema representing the entire recruitment lifecycle:
1. `User`: Recruiter and admin accounts, password hashes, and access roles.
2. `Job`: Job requisitions, job descriptions, work mode, and requisition mapping.
3. `Candidate`: Candidate master profiles, contact information, experience, and profile summaries.
4. `JobCandidate`: Pivot entity tracking candidate-job associations, recruitment lifecycle stages
   ('NEW', 'PENDING_OUTREACH', 'CONTACTED', 'INTERESTED', 'INTERVIEW_SCHEDULED'), interview appointment slots,
   online test links (`registration_url`), single-use `reschedule_token`, and reminder tracking flags.
5. `CandidateContact`: Complete audit log of inbound/outbound WhatsApp communications, intent classification,
   and provider delivery timestamps.
6. Legacy compatibility stubs: Dummy classes to prevent import breakages from older modules.
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
    """Base declarative class from which all NM-HireX database models inherit."""
    pass


# ============================================================
# 1. USERS (Authentication & Role Management)
# ============================================================
class User(Base):
    """Represents a recruiter, hiring manager, or administrator account.

    Stores authentication credentials, role assignments, and account activation states.
    """
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4,
        doc="Primary key UUID for user identification."
    )
    name: Mapped[str] = mapped_column(
        String(150), nullable=False,
        doc="Full display name of the user."
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False,
        doc="Unique login email address for authentication."
    )
    role: Mapped[str] = mapped_column(
        String(30), default="RECRUITER", nullable=False,
        doc="User role ('ADMIN' or 'RECRUITER') governing access control."
    )
    status: Mapped[str] = mapped_column(
        String(30), default="PENDING", nullable=False,
        doc="Approval status of the user account ('ACTIVE', 'PENDING', 'SUSPENDED')."
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        doc="Whether the user account is active. If False, login is denied."
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False,
        doc="Bcrypt-hashed password string."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        doc="Timestamp when user was created."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        doc="Timestamp when user was last updated."
    )


# ============================================================
# 2. JOBS (Role / Position container)
# ============================================================
class Job(Base):
    """Represents a job opening or requisition within the recruiting system.

    Maintains role details, requirements, work mode, and requisition linkages.
    """
    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4,
        doc="Primary key UUID for the job requisition."
    )
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True,
        doc="Foreign key to the User who created or owns this job."
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False,
        doc="Job title (e.g. 'Senior Python Developer')."
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        doc="Detailed job description and responsibilities."
    )
    location: Mapped[str | None] = mapped_column(
        String(255),
        doc="Job location (e.g. 'Noida, India', 'Remote')."
    )
    work_mode: Mapped[str | None] = mapped_column(
        String(50),
        doc="Work mode classification ('Onsite', 'Remote', 'Hybrid')."
    )
    status: Mapped[str] = mapped_column(
        String(50), default="ACTIVE", nullable=False,
        doc="Requisition status ('ACTIVE', 'CLOSED', 'ARCHIVED')."
    )
    requisition_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        doc="External requisition identifier mapped to gateway systems."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        doc="Timestamp when the job opening was created."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        doc="Timestamp when the job opening was last updated."
    )


# ============================================================
# 3. CANDIDATES (Candidate Profiles)
# ============================================================
class Candidate(Base):
    """Represents a candidate's master profile record.

    Contains personal contact details, total experience, current employer, and resume text.
    """
    __tablename__ = "candidates"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4,
        doc="Primary key UUID for the candidate."
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        doc="Full name of the candidate."
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        doc="Candidate's primary email address."
    )
    phone: Mapped[str | None] = mapped_column(
        String(50), index=True,
        doc="Normalized E.164 phone number used for WhatsApp messaging."
    )
    location: Mapped[str | None] = mapped_column(
        String(255),
        doc="Candidate's current residential city/region."
    )
    total_experience_years: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        doc="Total work experience in years."
    )
    current_company: Mapped[str | None] = mapped_column(
        String(255),
        doc="Candidate's current employer organization."
    )
    current_role: Mapped[str | None] = mapped_column(
        String(255),
        doc="Candidate's current job title or designation."
    )
    requisition_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        doc="External requisition ID associated with the candidate from outreach input."
    )
    notice_period_days: Mapped[int | None] = mapped_column(
        Integer,
        doc="Official notice period in calendar days."
    )
    profile_summary: Mapped[str | None] = mapped_column(
        Text,
        doc="AI or recruiter generated candidate profile summary."
    )
    raw_profile_text: Mapped[str | None] = mapped_column(
        Text,
        doc="Raw text extracted from candidate resume or profile import."
    )
    normalized_profile: Mapped[dict | None] = mapped_column(
        JSONB,
        doc="Parsed structured profile data (skills, history, education)."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        doc="Timestamp when candidate was first registered in NM-HireX."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        doc="Timestamp when candidate profile was last updated."
    )


# ============================================================
# 4. JOB_CANDIDATES (Recruitment Workflow, Status & Scheduling)
# ============================================================
class JobCandidate(Base):
    """Associates a Candidate with a specific Job opening and tracks pipeline status.

    Maintains candidate recruitment status, interview scheduling timestamps,
    assessment test URLs, automated reminder dispatch flags, and rescheduling tokens.
    """
    __tablename__ = "job_candidates"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4,
        doc="Primary key UUID for this specific job-candidate association."
    )
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True,
        doc="Foreign key to the Job requisition."
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True,
        doc="Foreign key to the Candidate profile."
    )
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True,
        doc="Optional tracking identifier for the candidate source."
    )
    eligibility_status: Mapped[str] = mapped_column(
        String(50), default="PENDING",
        doc="Candidate basic eligibility status ('ELIGIBLE', 'INELIGIBLE', 'PENDING')."
    )
    recruitment_status: Mapped[str] = mapped_column(
        String(50), default="NEW", index=True,
        doc="Current pipeline status ('NEW', 'PENDING_OUTREACH', 'CONTACTED', "
            "'INTERESTED', 'NOT_INTERESTED', 'INTERVIEW_SCHEDULED', 'COMPLETED', 'REJECTED')."
    )
    overall_score: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        doc="Matching score percentage (0-100) from evaluation."
    )
    classification: Mapped[str | None] = mapped_column(
        String(50),
        doc="Fit tier ('STRONG', 'MODERATE', 'LOW')."
    )
    is_shortlisted: Mapped[bool] = mapped_column(
        Boolean, default=False,
        doc="Whether the candidate is shortlisted for outreach."
    )
    ranking_position: Mapped[int | None] = mapped_column(
        Integer,
        doc="Numerical ranking position among applicants for this job."
    )
    interview_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        doc="Confirmed date and time of the candidate interview appointment."
    )
    interview_link: Mapped[str | None] = mapped_column(
        Text,
        doc="Candidate assessment link (e.g. Teckvalley portal or custom gateway test URL)."
    )
    registration_url: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        doc="Gateway test registration URL returned by external add-candidate API."
    )
    external_candidate_status: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        doc="External gateway candidate state."
    )
    request_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        doc="Gateway request identifier mapped to this scheduled candidate record."
    )
    requisition_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        doc="Gateway requisition identifier mapped to this candidate record."
    )
    reschedule_token: Mapped[str | None] = mapped_column(
        String(36), unique=True, index=True,
        doc="Single-use secure UUID token permitting 1 candidate self-reschedule."
    )
    reminder_24h_sent: Mapped[bool] = mapped_column(
        Boolean, default=False,
        doc="Atomic flag indicating if the 24-hour WhatsApp reminder was dispatched."
    )
    reminder_1h_sent: Mapped[bool] = mapped_column(
        Boolean, default=False,
        doc="Atomic flag indicating if the 1-hour WhatsApp reminder was dispatched."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        doc="Timestamp when candidate was associated with the job."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        doc="Timestamp when status was last modified."
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
    """Maintains a comprehensive audit log of candidate communications.

    Records outbound outreach dispatches, template sends, inbound candidate replies,
    NLP intent classification results, delivery provider message IDs, and read receipts.
    """
    __tablename__ = "candidate_contacts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4,
        doc="Primary key UUID for this contact communication event."
    )
    job_candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_candidates.id", ondelete="CASCADE"), nullable=False, index=True,
        doc="Foreign key to the specific JobCandidate association being contacted."
    )
    channel: Mapped[str | None] = mapped_column(
        String(50),
        doc="Communication channel ('WHATSAPP', 'EMAIL', 'SMS')."
    )
    message_type: Mapped[str | None] = mapped_column(
        String(100),
        doc="Direction and category ('OUTBOUND', 'INBOUND', 'TEMPLATE', 'CTA')."
    )
    message: Mapped[str | None] = mapped_column(
        Text,
        doc="Full content or body of the message sent or received."
    )
    provider: Mapped[str | None] = mapped_column(
        String(100),
        doc="Messaging service provider (e.g. 'NMVE')."
    )
    external_message_id: Mapped[str | None] = mapped_column(
        String(255), index=True,
        doc="Provider-assigned message ID for delivery status tracking."
    )
    status: Mapped[str | None] = mapped_column(
        String(50),
        doc="Delivery status ('SENT', 'DELIVERED', 'READ', 'FAILED', 'RECEIVED')."
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        doc="Timestamp when message was dispatched to the provider."
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        doc="Timestamp when recipient device acknowledged delivery."
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        doc="Timestamp when candidate opened and read the message."
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        doc="Timestamp when candidate sent a reply."
    )
    response_text: Mapped[str | None] = mapped_column(
        Text,
        doc="Exact text reply received from the candidate."
    )
    response_intent: Mapped[str | None] = mapped_column(
        String(50),
        doc="Evaluated intent classification ('INTERESTED', 'NOT_INTERESTED', 'UNKNOWN')."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow,
        doc="Timestamp when this contact record was created."
    )


# ============================================================
# LEGACY COMPATIBILITY STUBS (NOT registered as DB tables)
# These classes do NOT inherit from Base and are NOT created in PostgreSQL.
# Provided to prevent import errors in any older scripts.
# ============================================================
class _UnusedLegacyTable:
    """Stub class representing deprecated tables that are no longer part of NM-HireX."""
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
