"""NM-HireX Central API Routing Layer.

This module exposes the complete FastAPI REST routing surface for NM-HireX:
1. Authentication (`/api/auth/*`): Recruiter registration, login, and JWT token issuance.
2. WhatsApp Webhooks (`/api/webhooks/whatsapp`): Receives inbound candidate messages, classifies intent,
   and triggers automated scheduling link delivery.
3. Recruiter Pipeline & Jobs (`/api/user/*`, `/api/admin/*`): Dashboards, candidate management, status updates.
4. Candidate Self-Scheduling (`/api/scheduling/*`): Available date/time slot generator and slot booking
   endpoint that calls the Virtual Employee Gateway (`/add-candidate`) to generate test URLs.
5. One-Click Rescheduling (`/api/reschedule/{token}`): Token-validated candidate rescheduling portal.
6. Candidate Outreach Ingestion (`/api/outreach/*`): Bulk candidate ingestion (`/send-array`) supporting
   both automated WhatsApp outreach (`automate="yes"`) and manual review queues (`automate="no"`),
   as well as manual batch dispatching (`/send-pending`).
7. Gateway Integration Endpoints (`/api/gateway/*`): Proxy endpoints for external integration gateway APIs.
"""

from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import (
    create_access_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from .config import settings
from .database import get_db
from .models import Job, JobCandidate, User
from .tools_function import (
    get_admin_job_candidates,
    get_admin_jobs,
    get_job_candidates,
    get_outreach_candidates,
    get_user_dashboard,
    get_user_job_candidates,
    get_user_jobs,
    handle_whatsapp_webhook,
    schedule_candidate_interview,
    send_naukri_outreach_array,
    update_candidate_status,
    bulk_update_candidate_status,
    get_all_candidates,
    get_pending_outreach_candidates,
    send_pending_outreach_candidates,
)

# Main router for all application API endpoints with common prefix
router = APIRouter(prefix="/api")


# ============================================================
# REQUEST SCHEMAS (Pydantic Models)
# ============================================================
class ScheduleInterviewRequest(BaseModel):
    """Payload schema for manually scheduling an interview slot."""
    scheduled_at: datetime = Field(description="Target interview appointment timestamp in UTC/ISO format.")
    interview_link: str | None = Field(default=None, description="Optional custom interview URL.")


class InterviewStatusRequest(BaseModel):
    """Payload schema for updating a candidate interview progress status."""
    status: str = Field(description="New status string (e.g. 'SCHEDULED', 'COMPLETED', 'NO_SHOW').")


class CandidateStatusRequest(BaseModel):
    """Payload schema for single candidate recruitment status transition."""
    status: str = Field(description="Target recruitment status (e.g. 'CONTACTED', 'REJECTED').")
    target_phone: str | None = Field(default=None, description="Optional override phone for test dispatch.")


class BulkCandidateStatusRequest(BaseModel):
    """Payload schema for batch updating multiple candidate statuses simultaneously."""
    candidate_ids: list[UUID] = Field(description="Array of candidate UUIDs to update.")
    status: str = Field(default="CONTACTED", description="Status to apply across all candidates.")
    target_phone: str | None = Field(default=None, description="Optional override phone for testing.")


class RequisitionJobRequest(BaseModel):
    """Payload schema for requisition number lookups."""
    vereq_number: str = Field(min_length=1, description="Virtual Employee requisition identifier.")


class RescheduleRequest(BaseModel):
    """Payload schema for candidate interview rescheduling requests."""
    new_date: str = Field(description="Selected new calendar date (YYYY-MM-DD).")
    new_time: str = Field(description="Selected new time slot (HH:mm AM/PM).")
    timezone: str = Field(default="UTC", description="Candidate local timezone identifier.")


class NaukriCandidateItem(BaseModel):
    """Schema representing an individual candidate entry in outreach imports."""
    no: int | str | None = Field(default=None, description="Candidate serial number or phone index.")
    name: str = Field(description="Candidate full name.")
    role: str = Field(description="Target job title or role.")
    phone: str = Field(description="Contact mobile number.")


class NaukriOutreachRequest(BaseModel):
    """Payload schema for structured candidate array outreach imports."""
    job_id: UUID = Field(description="Job requisition UUID.")
    candidates: list[NaukriCandidateItem] = Field(description="List of candidate records to process.")
    company_name: str | None = Field(default=None, description="Display company name for WhatsApp template.")


# ============================================================
# HEALTH CHECK
# ============================================================
@router.get("/health")
def health():
    """Service health and liveness probe endpoint.

    Returns:
        dict: Service status confirmation.
    """
    return {"status": "ok", "service": "NM-HireX"}


# ============================================================
# AUTHENTICATION & RECRUITER ONBOARDING
# ============================================================
@router.post("/auth/register")
def register(
    name: str = Form(..., description="Recruiter full display name."),
    email: str = Form(..., description="Unique email address."),
    password: str = Form(..., description="Account password (minimum 8 characters)."),
    db: Session = Depends(get_db),
):
    """Register a new recruiter account in NM-HireX.

    Detailed Functionality:
    - Normalizes and validates email address.
    - Enforces minimum 8-character password constraint.
    - Prevents duplicate registration if email already exists in `users` table.
    - Hashes password using bcrypt.
    - Inserts new User with role 'RECRUITER' and status 'APPROVED'.

    Returns:
        dict: Success message and public user profile summary.

    Raises:
        HTTPException(400): If password is too short or email is already registered.
    """
    email = email.strip().lower()

    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters",
        )

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=400,
            detail="Email already registered",
        )

    user = User(
        name=name.strip(),
        email=email,
        password_hash=hash_password(password),
        role="RECRUITER",
        status="APPROVED",
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "User registered successfully",
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
        },
    }


@router.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate recruiter credentials and issue a signed JWT access token.

    Detailed Functionality:
    - Verifies user email existence in `users` table.
    - Validates account active state (`is_active == True`).
    - Validates password hash using constant-time bcrypt verification.
    - Issues JWT access token encoded with user claims (`sub`, `email`, `role`, `exp`).

    Returns:
        dict: Access token, token type ('bearer'), and user profile metadata.

    Raises:
        HTTPException(401): If credentials do not match or user does not exist.
        HTTPException(403): If user account is inactive or suspended.
    """
    email = form_data.username.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if (
        not user
        or not user.is_active
        or not user.password_hash
        or not verify_password(form_data.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status not in {"APPROVED", "ACTIVE", "PENDING"}:
        raise HTTPException(
            status_code=403,
            detail="User account is not active",
        )

    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
        },
    }


# @router.get("/auth/me")
# def me(user: User = Depends(get_current_user)):
#     return {
#         "id": str(user.id),
#         "name": user.name,
#         "email": user.email,
#         "role": user.role,
#         "status": user.status,
#         "is_active": user.is_active,
#     }





# ============================================================
# EXTERNAL RESUME MATCHING API - API 1
# ============================================================
# @router.get("/resume-matching/requisitions")
# def api_resume_matching_requisitions(
#     status: str | None = Query("open"),
#     department: str | None = Query(None),
#     q: str | None = Query(None),
#     # Backward-compatible alias; it is translated to the external API's `q`.
#     search: str | None = Query(None, include_in_schema=False),
#     period: str | None = Query(None),
#     created_from: str | None = Query(None),
#     created_to: str | None = Query(None),
#     sort: str | None = Query("status"),
#     limit: int = Query(50, ge=1, le=200),
#     offset: int = Query(0, ge=0),
#     include: str | None = Query(None),
#     user: User = Depends(get_current_user),
# ):
#     try:
#         effective_q = q or search
#         effective_include = include if include in {None, "details"} else None

#         return {
#             "success": True,
#             "data": get_resume_matching_requisitions(
#                 status=status,
#                 department=department,
#                 q=effective_q,
#                 period=period,
#                 created_from=created_from,
#                 created_to=created_to,
#                 sort=sort,
#                 limit=limit,
#                 offset=offset,
#                 include=effective_include,
#                 end_user=user.email,
#             ),
#         }
#     except Exception as exc:
#         raise HTTPException(
#             status_code=502,
#             detail=str(exc),
#         )


# ============================================================
# CREATE A LOCAL JOB FROM ONE VEREQ
# ============================================================
# @router.post("/resume-matching/requisitions/{vereq_number}/create-job")
# def api_create_job_from_vereq(
#     vereq_number: str,
#     user: User = Depends(get_current_user),
#     db: Session = Depends(get_db),
# ):
#     if user.role == "ADMIN":
#         raise HTTPException(
#             status_code=403,
#             detail="Admin cannot create jobs",
#         )

#     try:
#         job = create_job_from_resume_matching_requisition(
#             db=db,
#             user_id=user.id,
#             vereq_number=vereq_number,
#             end_user=user.email,
#         )
#         return {
#             "success": True,
#             "job_id": str(job.id),
#             "vereq_number": vereq_number,
#             "title": job.title,
#         }
#     except ValueError as exc:
#         raise HTTPException(
#             status_code=400,
#             detail=str(exc),
#         )
#     except Exception as exc:
#         db.rollback()
#         raise HTTPException(
#             status_code=502,
#             detail=str(exc),
#         )


# ============================================================
# EXTERNAL RESUME MATCHING API - API 2
# This is the point where the score/rank enters NM-HireX.
# ============================================================
# @router.post("/jobs/{job_id}/resume-matching")
# def api_resume_matching(
#     job_id: UUID,
#     vereq_number: str,
#     user: User = Depends(get_current_user),
#     db: Session = Depends(get_db),
# ):
#     job = db.get(Job, job_id)
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")

#     if user.role != "ADMIN" and job.created_by != user.id:
#         raise HTTPException(status_code=403, detail="Not your job")

#     try:
#         result = sync_resume_matching_candidates(
#             db=db,
#             job_id=job_id,
#             vereq_number=vereq_number,
#             top_n=100,
#             poll=True,
#             end_user=user.email,
#         )
#         return {
#             "success": True,
#             "message": "External matches saved successfully",
#             "data": result,
#         }
#     except Exception as exc:
#         db.rollback()
#         raise HTTPException(
#             status_code=502,
#             detail=str(exc),
#         )





# ============================================================
# CANDIDATES
# ============================================================
# @router.get("/jobs/{job_id}/candidates")
# def api_job_candidates(
#     job_id: UUID,
#     limit: int = Query(50, ge=1, le=100),
#     user: User = Depends(get_current_user),
#     db: Session = Depends(get_db),
# ):
#     job = db.get(Job, job_id)
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")

#     if user.role != "ADMIN" and job.created_by != user.id:
#         raise HTTPException(status_code=403, detail="Not your job")

#     return {
#         "success": True,
#         "data": get_job_candidates(db, job_id, limit=limit),
#     }


# ============================================================
# TOP 50 -> HISTORY CHECK -> WHATSAPP
# ============================================================
# @router.post("/jobs/{job_id}/outreach")
# def api_outreach(
#     job_id: UUID,
#     limit: int = Query(50, ge=1, le=50),
#     user: User = Depends(get_current_user),
#     db: Session = Depends(get_db),
# ):
#     job = db.get(Job, job_id)
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")

#     if user.role != "ADMIN" and job.created_by != user.id:
#         raise HTTPException(status_code=403, detail="Not your job")

#     return send_top_outreach(
#         db=db,
#         job_id=job_id,
#         limit=limit,
#     )


# ============================================================
# WHATSAPP WEBHOOK INGRESS
# ============================================================
@router.post("/webhooks/whatsapp")
def api_whatsapp_webhook(
    payload: dict,
    x_webhook_secret: str | None = Header(
        default=None,
        alias="X-Webhook-Secret",
        description="Optional shared secret header for verifying webhook authenticity.",
    ),
    db: Session = Depends(get_db),
):
    """Receive and process inbound WhatsApp webhook payloads from the NMVE integration.

    Detailed Functionality:
    - Validates optional `X-Webhook-Secret` header if configured in settings.
    - Extracts candidate phone number and inbound reply text.
    - Classifies candidate reply intent (e.g. 'INTERESTED', 'NOT_INTERESTED').
    - If 'INTERESTED', automatically dispatches the interview scheduling link (CTA).
    - If 'NOT_INTERESTED', records decline status and sends polite acknowledgment.
    - Logs all messages and delivery receipts in the `candidate_contacts` table.

    Returns:
        dict: Ingestion summary with classification intent and matched candidate IDs.
    """
    print("="*50)
    print("WHATSAPP WEBHOOK RECEIVED!")
    print(f"PAYLOAD: {payload}")
    print("="*50)

    if settings.WEBHOOK_SECRET:
        if x_webhook_secret != settings.WEBHOOK_SECRET:
            raise HTTPException(
                status_code=401,
                detail="Invalid webhook secret",
            )

    return handle_whatsapp_webhook(
        db=db,
        payload=payload,
    )


# ============================================================
# USER & ADMIN VIEWS (Jobs, Candidates, Dashboards)
# ============================================================
@router.get("/user/jobs")
def api_user_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all job requisitions created by the currently authenticated recruiter.

    Returns:
        list[dict]: Array of job definitions belonging to the current user.
    """
    return get_user_jobs(db, user.id)


@router.post("/user/jobs/{job_id}/candidates/{candidate_id}/status")
def api_update_candidate_status(
    job_id: UUID,
    candidate_id: UUID,
    data: CandidateStatusRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a candidate's recruitment lifecycle status for a job opening.

    Detailed Functionality:
    - Validates that the job exists and belongs to the authenticated user (or user is ADMIN).
    - If transitioned to 'CONTACTED', automatically sends the initial WhatsApp template.

    Returns:
        dict: Success status and updated candidate status details.

    Raises:
        HTTPException(403): If the user does not have permission to modify the job.
        HTTPException(404): If the job requisition is not found.
    """
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if user.role != "ADMIN" and job.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not your job")

    try:
        return {
            "success": True,
            "data": update_candidate_status(
                db=db,
                job_id=job_id,
                candidate_id=candidate_id,
                status=data.status,
                target_phone=data.target_phone,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/user/jobs/{job_id}/candidates/bulk-status")
def api_bulk_update_candidate_status(
    job_id: UUID,
    data: BulkCandidateStatusRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Batch-update recruitment status for multiple candidates associated with a job.

    Returns:
        dict: Summary containing counts of successful updates and individual results.
    """
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if user.role != "ADMIN" and job.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not your job")

    try:
        return {
            "success": True,
            "data": bulk_update_candidate_status(
                db=db,
                job_id=job_id,
                candidate_ids=data.candidate_ids,
                status=data.status,
                target_phone=data.target_phone,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/user/jobs/{job_id}/candidates")
def api_user_candidates(
    job_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List ranked and shortlisted candidates for a recruiter's job requisition.

    Returns:
        list[dict]: Array of candidate profiles ranked by matching score.
    """
    try:
        return get_user_job_candidates(db, user.id, job_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not your job")


@router.get("/admin/jobs")
def api_admin_jobs(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only endpoint listing all jobs across the platform with recruiter metadata.

    Returns:
        list[dict]: Global job catalog with uploader information and candidate previews.
    """
    return get_admin_jobs(db)


@router.get("/admin/jobs/{job_id}/candidates")
def api_admin_candidates(
    job_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin-only endpoint listing candidates for any job in the system without ownership checks.

    Returns:
        list[dict]: Ranked candidate profiles.
    """
    try:
        return get_admin_job_candidates(db, job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/user/dashboard")
def api_user_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve recruiter dashboard metrics, funnel conversion KPIs, and recent candidates.

    Returns:
        dict: Aggregate statistics (invites sent, interested, scheduled, delivery rates).
    """
    return get_user_dashboard(db, user.id)


@router.get("/user/outreach")
def api_user_outreach(
    candidate_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve all candidates actively engaged in the WhatsApp outreach pipeline.

    Returns:
        list[dict]: Candidate pipeline records with latest inbound reply and delivery statuses.
    """
    return get_outreach_candidates(db, user.id, candidate_id=candidate_id)


@router.get("/user/candidates")
def api_user_all_candidates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve unique candidates progressing through active interview stages.

    Returns:
        list[dict]: Array of distinct candidate profiles currently in interview workflow.
    """
    return get_all_candidates(db, user.id)

# ============================================================
# CANDIDATE SELF-SCHEDULING & RESCHEDULING ENGINE
# ============================================================
class ScheduleConfirmRequest(BaseModel):
    """Payload schema for candidate interview slot confirmation."""
    job_candidate_id: UUID = Field(description="Target JobCandidate schedule record UUID.")
    interview_date: str = Field(description="Selected interview date (YYYY-MM-DD).")
    interview_time: str = Field(description="Selected interview time (e.g. '11:00 AM' or '14:30').")
    timezone: str = Field(default="Asia/Kolkata", description="Candidate local timezone identifier.")


def parse_interview_datetime(date_str: str, time_str: str) -> datetime:
    """Robustly parse date and time strings across multiple standard and international formats.

    Detailed Functionality:
    - Normalizes date and time strings.
    - Sequentially attempts parsing against standard date formats:
      * '%Y-%m-%d %I:%M %p'
      * '%Y-%m-%d %I:%M%p'
      * '%Y-%m-%d %H:%M:%S'
      * '%Y-%m-%d %H:%M'
      * '%Y-%m-%d %I %p'
    - Falls back to `dateutil.parser` for any non-standard locale formats.

    Parameters:
        date_str (str): Calendar date string.
        time_str (str): Time string.

    Returns:
        datetime: Parsed Python datetime object.

    Raises:
        HTTPException(400): If the format cannot be parsed.
    """
    time_clean = time_str.strip().upper()
    combined = f"{date_str.strip()} {time_clean}"
    
    formats = [
        "%Y-%m-%d %I:%M %p",
        "%Y-%m-%d %I:%M%p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %I %p",
        "%Y-%m-%d %I%p",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            pass
            
    try:
        from dateutil import parser
        return parser.parse(f"{date_str} {time_str}")
    except Exception:
        pass

    raise HTTPException(status_code=400, detail=f"Invalid date/time format: '{date_str}' '{time_str}'")


@router.get("/scheduling/dates")
def api_scheduling_dates(timezone: str | None = "Asia/Kolkata"):
    """Generate available interview dates starting from today in the candidate's timezone.

    Detailed Functionality:
    - Resolves candidate timezone using `zoneinfo.ZoneInfo` (defaulting to 'Asia/Kolkata').
    - Returns a list of the next 7 consecutive dates available for booking.

    Returns:
        dict: List of ISO date strings (`{"dates": [{"date": "2026-11-10"}, ...]}`).
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    tz_name = timezone or "Asia/Kolkata"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")

    today = datetime.now(tz).date()
    dates = []
    # Provide next 7 days starting from today in candidate's timezone
    for i in range(0, 8):
        d = today + timedelta(days=i)
        dates.append({"date": d.isoformat()})
    return {"dates": dates}


@router.get("/scheduling/slots")
def api_scheduling_slots(
    date: str | None = None,
    timezone: str | None = "Asia/Kolkata",
):
    """Generate available 30-minute time slots for a given date in the candidate's timezone.

    Detailed Functionality:
    - Generates 30-minute interview intervals across 24 hours (e.g. '09:00 AM', '09:30 AM').
    - If the requested date is today in the candidate's timezone, filters out time slots
      that have already elapsed in wall-clock time.
    - If the date is entirely in the past, returns an empty slot list.

    Returns:
        dict: List of formatted slot strings (`{"slots": ["10:00 AM", "10:30 AM", ...]}`).
    """
    from zoneinfo import ZoneInfo
    tz_name = timezone or "Asia/Kolkata"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")

    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    slots = []
    for hour in range(24):
        for minute in (0, 30):
            # If the requested date is today in the candidate's timezone, filter out past slots
            if date == today_str:
                slot_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                # Filter out any slot that has already passed (or is right now)
                if slot_dt <= now:
                    continue
            elif date and date < today_str:
                # If the entire date is in the past, no slots are available
                continue

            h12 = hour % 12
            if h12 == 0:
                h12 = 12
            ampm = "AM" if hour < 12 else "PM"
            slots.append(f"{h12:02d}:{minute:02d} {ampm}")
    return {"slots": slots}


@router.post("/scheduling/confirm")
def api_scheduling_confirm(
    req: ScheduleConfirmRequest,
    db: Session = Depends(get_db)
):
    """Confirm a candidate's selected interview appointment slot.

    Detailed Workflow:
    1. Validation: Parses datetime and verifies that the selected appointment is in the future.
    2. Gateway Registration & Link Creation:
       - Calls the external Virtual Employee Gateway write API (`add_candidate`) using Key 2.
       - Maps `request_id = jc.id` and `requisition_id = cand.id`.
       - Captures the generated `registrationUrl` (custom assessment test link).
       - Persists `registrationUrl` to `job_candidates.registration_url`.
    3. Interview Scheduling:
       - Calls `schedule_candidate_interview()`.
       - Issues single-use `reschedule_token`.
       - Sets `recruitment_status = 'INTERVIEW_SCHEDULED'`.
       - Normalizes test link to `https://interview.teckvalley.com/` if no custom URL returned.
    4. WhatsApp Confirmation:
       - Dispatches WhatsApp confirmation to the candidate via Key 1 containing test link and reschedule URL.

    Returns:
        dict: Confirmation payload with meeting link and formatted scheduled time.
    """
    from zoneinfo import ZoneInfo
    from .tools_function import schedule_candidate_interview
    
    dt = parse_interview_datetime(req.interview_date, req.interview_time)
    
    # Validate that the selected interview time is in the future
    try:
        tz = ZoneInfo(req.timezone or "Asia/Kolkata")
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    now_in_tz = datetime.now(tz).replace(tzinfo=None)
    if dt <= now_in_tz:
        raise HTTPException(
            status_code=400,
            detail="Cannot schedule an interview in the past. Please select a future time slot."
        )

    # -------------------------------------------------------------
    # Call WhatsApp Gateway /add-candidate and use registrationUrl
    # in place of Teams meeting link (dont send teams now)
    # -------------------------------------------------------------
    meeting_url = None
    from .models import JobCandidate, Candidate, Job
    from .gateway_service import add_candidate
    
    jc = db.get(JobCandidate, req.job_candidate_id)
    cand = db.get(Candidate, jc.candidate_id) if jc else None
    job = db.get(Job, jc.job_id) if jc and jc.job_id else None

    if cand:
        try:
            cand_name = cand.name or "Candidate"
            cand_phone = cand.phone or ""
            cand_email = cand.email or f"{cand_phone or 'candidate'}@nmhirex.com"
            cand_company = cand.current_company or ""
            cand_role = cand.current_role or (job.title if job else "")
            
            # The candidates table id as requisition_id
            requisition_id = str(cand.id)
            # When interview scheduled, the record stored in database as request_id
            request_id = str(jc.id)

            # Store request_id and requisition_id for this candidate in the database
            jc.request_id = request_id
            jc.requisition_id = requisition_id
            db.commit()

            cand_exp_val = ""
            if cand.total_experience_years is not None:
                cand_exp_val = str(cand.total_experience_years).rstrip("0").rstrip(".")

            gw_payload = {
                "user_name": cand_name,
                "email": cand_email,
                "contact_no": cand_phone,
                "current_company": cand_company,
                "interview_date": dt.strftime("%Y-%m-%d"),
                "interview_time": dt.strftime("%H:%M"),
                "experience": cand_exp_val,
                "technical_round": 1,
                "one2one_round": 1,
                "comm_skill_rating": 4,
                "cultural_fit_rating": 4,
                "operation": "addcandidate",
                "request_id": request_id,
                "requisition_id": requisition_id,
                "job_role": cand_role,
            }
            gw_res = add_candidate(gw_payload)
            meeting_url = gw_res.get("registrationUrl")
            if meeting_url:
                jc.registration_url = meeting_url
                db.commit()
        except Exception as gw_err:
            import logging
            logging.getLogger("nmhirex").warning("Gateway add_candidate failed during slot confirmation: %s", gw_err)

    # Send registrationUrl / test URL in place of Teams link (do not send teams)
    interview_link = meeting_url or "https://interview.teckvalley.com/"
    teams_link = interview_link
    
    res = schedule_candidate_interview(
        db=db,
        job_candidate_id=req.job_candidate_id,
        scheduled_at=dt,
        interview_link=teams_link,
        is_reschedule=False,
    )
    
    return {
        "success": True, 
        "data": {
            "link": teams_link,
            "scheduled_at": dt.strftime("%Y-%m-%dT%H:%M:%S")
        }
    }


@router.get("/reschedule/{token}")
def api_get_reschedule_details(token: str, db: Session = Depends(get_db)):
    """Fetch existing interview details for a candidate accessing the reschedule portal.

    Detailed Functionality:
    - Validates that the single-use `reschedule_token` exists and has not already been used.
    - Retrieves candidate name, job title, and current appointment timestamp.

    Returns:
        dict: Existing interview details for display on `/reschedule/{token}`.

    Raises:
        HTTPException(404): If token is expired or invalid.
    """
    from .models import JobCandidate, Candidate, Job
    jc = db.query(JobCandidate).filter(JobCandidate.reschedule_token == token).first()
    if not jc:
        raise HTTPException(
            status_code=404,
            detail="This reschedule link has already been used or is expired. Interviews can only be rescheduled once."
        )
        
    candidate = db.get(Candidate, jc.candidate_id)
    job = db.get(Job, jc.job_id)
    
    return {
        "success": True,
        "data": {
            "candidate_name": candidate.name if candidate else "Candidate",
            "job_title": job.title if job else "Interview",
            "current_scheduled_at": (
                jc.interview_scheduled_at.strftime("%Y-%m-%dT%H:%M:%S")
                if jc.interview_scheduled_at
                else None
            ),
            "interview_link": jc.interview_link or f"https://teams.microsoft.com/l/meetup-join/nmhirex-{jc.id}"
        }
    }


@router.post("/reschedule/{token}")
def api_post_reschedule(token: str, req: RescheduleRequest, db: Session = Depends(get_db)):
    """Submit a new interview appointment time via candidate one-click rescheduling.

    Detailed Functionality:
    - Validates single-use `reschedule_token`.
    - Parses new date and time, verifying it is strictly in the future.
    - Updates `interview_scheduled_at` timestamp.
    - Resets reminder flags (`reminder_24h_sent = False`, `reminder_1h_sent = False`).
    - Invalidates `reschedule_token = None` (enforcing single-reschedule policy).
    - Dispatches WhatsApp rescheduling confirmation message.

    Returns:
        dict: Success message with updated appointment datetime and meeting link.

    Raises:
        HTTPException(400): If new appointment time is in the past.
        HTTPException(404): If token is invalid or already consumed.
    """
    from zoneinfo import ZoneInfo
    from .models import JobCandidate
    from .tools_function import schedule_candidate_interview
    
    jc = db.query(JobCandidate).filter(JobCandidate.reschedule_token == token).first()
    if not jc:
        raise HTTPException(
            status_code=404,
            detail="This reschedule link has already been used or is expired. Interviews can only be rescheduled once."
        )
        
    dt = parse_interview_datetime(req.new_date, req.new_time)
    
    # Validate that the selected reschedule time is in the future
    try:
        tz = ZoneInfo(req.timezone or "Asia/Kolkata")
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    now_in_tz = datetime.now(tz).replace(tzinfo=None)
    if dt <= now_in_tz:
        raise HTTPException(
            status_code=400,
            detail="Cannot schedule an interview in the past. Please select a future time slot."
        )

    existing_link = jc.interview_link
    if existing_link and "teams.microsoft.com" in existing_link:
        existing_link = None
    teams_link = existing_link or "https://interview.teckvalley.com/"
    
    res = schedule_candidate_interview(
        db=db,
        job_candidate_id=jc.id,
        scheduled_at=dt,
        interview_link=teams_link,
        is_reschedule=True,
    )
    
    return {
        "success": True,
        "message": "Interview rescheduled successfully",
        "data": {
            "link": teams_link,
            "scheduled_at": dt.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    }


# ============================================================
# CANDIDATE OUTREACH & BATCH ARRAY INGESTION
# ============================================================
@router.post("/outreach/send-array")
@router.post("/outreach/invite")
async def api_send_outreach_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """Ingest an array or single candidate object for recruitment outreach.

    Detailed Functionality:
    - Flexible payload ingestion: supports a JSON array of candidates, a single candidate object,
      or a wrapped envelope `{"candidates": [...], "company_name": "...", "automate": "yes"}`.
    - Decodes Bearer token if present to attribute created jobs to the authenticated recruiter;
      otherwise falls back to the default system Admin user.
    - Automation Routing based on `automate`:
      * If `automate="yes"`: dispatches initial WhatsApp template invitation immediately via Key 1,
        logs message in `candidate_contacts`, and advances candidate to 'CONTACTED'.
      * If `automate="no"`: records candidate in database with status 'PENDING_OUTREACH',
        making them available for recruiter review and manual dispatch on `/outreach/pending`.

    Returns:
        dict: Execution summary with total, sent, queued, and skipped candidate metrics.

    Raises:
        HTTPException(400): If payload is not valid JSON or lacks mandatory candidate fields.
        HTTPException(500): On unhandled database or processing exceptions.
    """
    from jose import jwt, JWTError

    user = None
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            user_id = payload.get("sub")
            if user_id:
                user = db.get(User, UUID(str(user_id)))
        except (JWTError, ValueError, TypeError):
            user = None

    if not user:
        user = db.scalar(select(User).limit(1))
        if not user:
            from .auth import hash_password
            user = User(
                name="NM-HireX Admin",
                email="admin@nmhirex.com",
                password_hash=hash_password("Admin@123456"),
                role="ADMIN",
                status="APPROVED",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    candidates_list = []
    job_id = None
    company_name = None
    automate = "yes"

    if isinstance(body, list):
        candidates_list = body
    elif isinstance(body, dict):
        automate = body.get("automate", "yes")
        if "candidates" in body and isinstance(body["candidates"], list):
            candidates_list = body["candidates"]
            job_id = body.get("job_id")
            company_name = body.get("company_name")
        elif ("name" in body or "user_name" in body) and (
            "phone" in body
            or "no" in body
            or "phone_number" in body
            or "mobile" in body
            or "contact_no" in body
        ):
            candidates_list = [body]
            job_id = body.get("job_id")
            company_name = body.get("company_name")
        else:
            raise HTTPException(
                status_code=400,
                detail="Expected an array of candidate objects with 'name', 'role', and 'no' (or 'phone')",
            )
    else:
        raise HTTPException(status_code=400, detail="Payload must be a JSON array or object")

    parsed_job_uuid = None
    if job_id:
        try:
            parsed_job_uuid = UUID(str(job_id))
        except (ValueError, TypeError):
            parsed_job_uuid = None

    try:
        result = send_naukri_outreach_array(
            db=db,
            job_id=parsed_job_uuid,
            candidates=candidates_list,
            company_name=company_name,
            user_id=user.id if user else None,
            automate=automate,
        )
        return {"success": True, "data": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


class SendPendingOutreachRequest(BaseModel):
    """Payload schema for sending WhatsApp invites to selected pending candidates."""
    job_candidate_ids: list[UUID] = Field(description="Array of JobCandidate UUIDs selected for outreach.")


@router.get("/outreach/pending")
def api_get_pending_outreach(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve candidates queued for manual outreach review (`recruitment_status='PENDING_OUTREACH'`).

    Detailed Functionality:
    - Queries all candidate records currently in the manual review queue that have not yet
      received an outbound WhatsApp invitation.
    - Used by the `/outreach/pending` frontend page to present selectable candidate tables.

    Returns:
        list[dict]: Array of candidate objects with company, role, phone, and experience.
    """
    return get_pending_outreach_candidates(db, user_id=user.id if user else None)


@router.post("/outreach/send-pending")
def api_send_pending_outreach(
    req: SendPendingOutreachRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dispatch WhatsApp invitations to recruiter-selected candidates from the pending queue.

    Detailed Functionality:
    - Called when a recruiter selects one, multiple, or all candidates on `/outreach/pending`
      and clicks the WhatsApp icon action button.
    - Dispatches WhatsApp template message via Key 1 (`WHATSAPP_MESSAGE_API_KEY`).
    - Updates candidate status to 'CONTACTED' and logs contact history.

    Returns:
        dict: Summary of dispatched messages (sent, failed, skipped).
    """
    try:
        res = send_pending_outreach_candidates(db, req.job_candidate_ids)
        return {"success": True, "data": res}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))



# ============================================================
# WHATSAPP INTEGRATION GATEWAY PROXY ENDPOINTS (Key 2)
# ============================================================
from .gateway_client import (
    GatewayError,
    GatewayAuthError,
    GatewayForbiddenError,
    GatewayValidationError,
    GatewayRateLimitError,
    GatewayServerError,
    GatewayConnectionError,
)
from .gateway_service import (
    fetch_schedules,
    fetch_interview_results,
    add_candidate,
    fetch_joined_interview_data,
)


def _handle_gateway_exception(exc: Exception):
    """Translate low-level typed GatewayError exceptions into structured FastAPI HTTPExceptions.

    Detailed Functionality:
    - Extracts HTTP status code, request ID, and specific error code from `GatewayError`.
    - Formats a clean JSON error response for API callers.
    - Catches unexpected non-gateway exceptions and converts them to HTTP 500.

    Parameters:
        exc (Exception): Caught exception instance.

    Raises:
        HTTPException: Normalized FastAPI HTTPException.
    """
    if isinstance(exc, GatewayError):
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "success": False,
                "message": exc.message,
                "requestId": exc.request_id,
                "code": exc.error_code or f"HTTP_{exc.status_code}",
            },
        )
    raise HTTPException(
        status_code=500,
        detail={
            "success": False,
            "message": str(exc),
            "requestId": None,
            "code": "INTERNAL_SERVER_ERROR",
        },
    )


@router.post("/gateway/schedules")
def api_post_gateway_schedules(filters: dict = Body(default={})):
    """Retrieve scheduled interviews from WhatsApp Gateway via POST filter body.

    Returns:
        dict: List of scheduled interviews aggregated across all pages.
    """
    try:
        return fetch_schedules(filters)
    except Exception as exc:
        _handle_gateway_exception(exc)


@router.get("/gateway/schedules")
def api_get_gateway_schedules(
    page: int = Query(1, description="Page index."),
    pageSize: int = Query(50, description="Items per page."),
    startDate: str | None = Query(None, description="Start date filter (YYYY-MM-DD)."),
    endDate: str | None = Query(None, description="End date filter (YYYY-MM-DD)."),
    date: str | None = Query(None, description="Specific calendar date."),
    dateType: str | None = Query("interview_date", description="Field to filter date on."),
    is_registered: bool | None = Query(None, description="Filter by candidate registration status."),
    requisition_id: str | None = Query(None, description="Requisition filter."),
    candidate_email: str | None = Query(None, description="Candidate email search."),
    added_by_email: str | None = Query(None, description="Recruiter email."),
    search: str | None = Query(None, description="Free-text search term."),
    all: bool | None = Query(None, description="Fetch all flag."),
    auto_paginate: bool = Query(True, description="Whether to iterate through all pages automatically."),
):
    """Retrieve scheduled interviews from WhatsApp Gateway via query parameters (GET).

    Returns:
        dict: Standardized schedule list with pagination metrics.
    """
    filters = {
        "page": page,
        "pageSize": pageSize,
        "dateType": dateType,
    }
    if startDate:
        filters["startDate"] = startDate
    if endDate:
        filters["endDate"] = endDate
    if date:
        filters["date"] = date
    if is_registered is not None:
        filters["is_registered"] = is_registered
    if requisition_id:
        filters["requisition_id"] = requisition_id
    if candidate_email:
        filters["candidate_email"] = candidate_email
    if added_by_email:
        filters["added_by_email"] = added_by_email
    if search:
        filters["search"] = search
    if all is not None:
        filters["all"] = all

    try:
        return fetch_schedules(filters, auto_paginate=auto_paginate)
    except Exception as exc:
        _handle_gateway_exception(exc)


@router.post("/gateway/interview-results")
def api_post_gateway_interview_results(filters: dict = Body(default={})):
    """Retrieve candidate interview assessment results from WhatsApp Gateway via POST body.

    Returns:
        dict: Array of candidate scores, outcomes, and feedback across pages.
    """
    try:
        return fetch_interview_results(filters)
    except Exception as exc:
        _handle_gateway_exception(exc)


@router.get("/gateway/interview-results")
def api_get_gateway_interview_results(
    page: int = Query(1, description="Page index."),
    pageSize: int = Query(50, description="Items per page."),
    startDate: str | None = Query(None, description="Start date filter."),
    endDate: str | None = Query(None, description="End date filter."),
    date: str | None = Query(None, description="Specific date filter."),
    requisition_id: str | None = Query(None, description="Requisition ID filter."),
    candidate_email: str | None = Query(None, description="Candidate email lookup."),
    user_id: str | None = Query(None, description="Candidate ID filter."),
    added_by_email: str | None = Query(None, description="Recruiter email filter."),
    test_type: int | None = Query(None, description="Assessment test type ID."),
    result: str | None = Query(None, description="Outcome filter ('Pass', 'Fail')."),
    search: str | None = Query(None, description="Text search."),
    all: bool | None = Query(None, description="Fetch all records flag."),
    auto_paginate: bool = Query(True, description="Iterate all pages."),
):
    """Retrieve candidate interview assessment results from WhatsApp Gateway via query parameters (GET).

    Returns:
        dict: Standardized candidate test results with pagination metadata.
    """
    filters = {
        "page": page,
        "pageSize": pageSize,
    }
    if startDate:
        filters["startDate"] = startDate
    if endDate:
        filters["endDate"] = endDate
    if date:
        filters["date"] = date
    if requisition_id:
        filters["requisition_id"] = requisition_id
    if candidate_email:
        filters["candidate_email"] = candidate_email
    if user_id:
        filters["user_id"] = user_id
    if added_by_email:
        filters["added_by_email"] = added_by_email
    if test_type is not None:
        filters["test_type"] = test_type
    if result:
        filters["result"] = result
    if search:
        filters["search"] = search
    if all is not None:
        filters["all"] = all

    try:
        return fetch_interview_results(filters, auto_paginate=auto_paginate)
    except Exception as exc:
        _handle_gateway_exception(exc)


@router.get("/gateway/interviews-joined")
def api_get_gateway_joined_interviews(
    startDate: str | None = Query(None, description="Start date filter."),
    endDate: str | None = Query(None, description="End date filter."),
    requisition_id: str | None = Query(None, description="Requisition ID filter."),
    search: str | None = Query(None, description="Candidate search term."),
):
    """Fetch schedules and interview assessment results merged relationally on `schedule_id` and `requisition_id`.

    Returns:
        dict: Merged dataset combining interview schedules with final test scores.
    """
    filters = {}
    if startDate:
        filters["startDate"] = startDate
    if endDate:
        filters["endDate"] = endDate
    if requisition_id:
        filters["requisition_id"] = requisition_id
    if search:
        filters["search"] = search

    try:
        return fetch_joined_interview_data(filters)
    except Exception as exc:
        _handle_gateway_exception(exc)


@router.post("/gateway/add-candidate")
@router.post("/gateway/candidates")
def api_post_gateway_add_candidate(
    candidate_input: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Register candidate on WhatsApp Gateway, schedule interview, and persist records in DB.

    Detailed Workflow:
    - Strips internal `automate` flag so it never leaks upstream.
    - Finds or creates `Candidate`, `Job`, and `JobCandidate` records in PostgreSQL.
    - Sets `requisition_id` to candidate UUID and `request_id` to schedule UUID.
    - Calls external Gateway write API (`/api/integrations/whatsapp/raw/add-candidate`) via Key 2.
    - Captures the generated `registrationUrl` (custom online test link).
    - Saves `registrationUrl` and updates recruitment status to 'INTERVIEW_SCHEDULED'.

    Returns:
        dict: Gateway response containing candidate ID and `registrationUrl`.
    """
    try:
        # Strictly ensure 'automate' key is never forwarded to add-candidate gateway API
        candidate_input.pop("automate", None)

        from .models import Candidate, JobCandidate, Job, User
        from .tools_function import _clean_whatsapp_phone
        from sqlalchemy import select

        c_name = str(candidate_input.get("user_name") or candidate_input.get("name") or "").strip()
        c_phone = str(candidate_input.get("contact_no") or candidate_input.get("phone") or candidate_input.get("no") or "").strip()
        c_email = str(candidate_input.get("email") or "").strip()
        c_company = str(candidate_input.get("current_company") or candidate_input.get("company") or "").strip()
        c_role = str(candidate_input.get("job_role") or candidate_input.get("role") or "").strip()
        c_date = str(candidate_input.get("interview_date") or "").strip()
        c_time = str(candidate_input.get("interview_time") or "").strip()

        cand = None
        clean_phone = _clean_whatsapp_phone(c_phone) if c_phone else ""
        if clean_phone:
            cand = db.scalar(select(Candidate).where(Candidate.phone == clean_phone))
        if not cand and c_email:
            cand = db.scalar(select(Candidate).where(Candidate.email == c_email))

        if not cand and c_name:
            cand = Candidate(
                name=c_name,
                phone=clean_phone or c_phone,
                email=c_email if c_email else None,
                current_company=c_company if c_company else None,
                current_role=c_role if c_role else None,
            )
            db.add(cand)
            db.flush()

        # Requisition ID: use Candidate table id
        if cand and not candidate_input.get("requisition_id"):
            candidate_input["requisition_id"] = str(cand.id)

        # Job & JobCandidate for interview schedule
        jc = None
        if cand:
            job = db.scalar(select(Job).where(Job.title == (c_role or "General Position")).limit(1))
            if not job:
                user = db.scalar(select(User).limit(1))
                job = Job(
                    title=c_role or "General Position",
                    status="ACTIVE",
                    created_by=user.id if user else None,
                )
                db.add(job)
                db.flush()

            jc = db.scalar(
                select(JobCandidate).where(
                    JobCandidate.job_id == job.id,
                    JobCandidate.candidate_id == cand.id,
                )
            )
            if not jc:
                jc = JobCandidate(
                    job_id=job.id,
                    candidate_id=cand.id,
                    is_shortlisted=True,
                    recruitment_status="INTERVIEW_SCHEDULED",
                )
                db.add(jc)
                db.flush()

            if c_date and c_time:
                try:
                    dt = parse_interview_datetime(c_date, c_time)
                    jc.interview_scheduled_at = dt
                    jc.recruitment_status = "INTERVIEW_SCHEDULED"
                except Exception:
                    pass

            db.commit()

            # Request ID: interview scheduled record stored in database
            if not candidate_input.get("request_id"):
                candidate_input["request_id"] = str(jc.id)

            jc.request_id = str(candidate_input["request_id"])
            jc.requisition_id = str(candidate_input.get("requisition_id") or cand.id)
            db.commit()

        res = add_candidate(candidate_input)

        reg_url = res.get("registrationUrl")
        if jc and reg_url:
            jc.interview_link = reg_url
            jc.registration_url = reg_url
            db.commit()

        return {
            "success": True,
            "message": "Candidate created and interview scheduled successfully.",
            "registrationUrl": res.get("registrationUrl"),
            "data": res,
        }
    except Exception as exc:
        db.rollback()
        _handle_gateway_exception(exc)
    try:
        # Strictly ensure 'automate' key is never forwarded to add-candidate gateway API
        candidate_input.pop("automate", None)

        from .models import Candidate, JobCandidate, Job, User
        from .tools_function import _clean_whatsapp_phone
        from sqlalchemy import select

        c_name = str(candidate_input.get("user_name") or candidate_input.get("name") or "").strip()
        c_phone = str(candidate_input.get("contact_no") or candidate_input.get("phone") or candidate_input.get("no") or "").strip()
        c_email = str(candidate_input.get("email") or "").strip()
        c_company = str(candidate_input.get("current_company") or candidate_input.get("company") or "").strip()
        c_role = str(candidate_input.get("job_role") or candidate_input.get("role") or "").strip()
        c_date = str(candidate_input.get("interview_date") or "").strip()
        c_time = str(candidate_input.get("interview_time") or "").strip()

        cand = None
        clean_phone = _clean_whatsapp_phone(c_phone) if c_phone else ""
        if clean_phone:
            cand = db.scalar(select(Candidate).where(Candidate.phone == clean_phone))
        if not cand and c_email:
            cand = db.scalar(select(Candidate).where(Candidate.email == c_email))

        if not cand and c_name:
            cand = Candidate(
                name=c_name,
                phone=clean_phone or c_phone,
                email=c_email if c_email else None,
                current_company=c_company if c_company else None,
                current_role=c_role if c_role else None,
            )
            db.add(cand)
            db.flush()

        # Requisition ID: use Candidate table id
        if cand and not candidate_input.get("requisition_id"):
            candidate_input["requisition_id"] = str(cand.id)

        # Job & JobCandidate for interview schedule
        jc = None
        if cand:
            job = db.scalar(select(Job).where(Job.title == (c_role or "General Position")).limit(1))
            if not job:
                user = db.scalar(select(User).limit(1))
                job = Job(
                    title=c_role or "General Position",
                    status="ACTIVE",
                    created_by=user.id if user else None,
                )
                db.add(job)
                db.flush()

            jc = db.scalar(
                select(JobCandidate).where(
                    JobCandidate.job_id == job.id,
                    JobCandidate.candidate_id == cand.id,
                )
            )
            if not jc:
                jc = JobCandidate(
                    job_id=job.id,
                    candidate_id=cand.id,
                    is_shortlisted=True,
                    recruitment_status="INTERVIEW_SCHEDULED",
                )
                db.add(jc)
                db.flush()

            if c_date and c_time:
                try:
                    dt = parse_interview_datetime(c_date, c_time)
                    jc.interview_scheduled_at = dt
                    jc.recruitment_status = "INTERVIEW_SCHEDULED"
                except Exception:
                    pass

            db.commit()

            # Request ID: interview scheduled record stored in database
            if not candidate_input.get("request_id"):
                candidate_input["request_id"] = str(jc.id)

            jc.request_id = str(candidate_input["request_id"])
            jc.requisition_id = str(candidate_input.get("requisition_id") or cand.id)
            db.commit()

        res = add_candidate(candidate_input)

        reg_url = res.get("registrationUrl")
        if jc and reg_url:
            jc.interview_link = reg_url
            jc.registration_url = reg_url
            db.commit()

        return {
            "success": True,
            "message": "Candidate created and interview scheduled successfully.",
            "registrationUrl": res.get("registrationUrl"),
            "data": res,
        }
    except Exception as exc:
        db.rollback()
        _handle_gateway_exception(exc)
