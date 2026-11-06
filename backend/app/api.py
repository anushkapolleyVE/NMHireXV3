"""NM-HireX API routes.

The new recruitment flow starts after the external Resume Matching API has
already produced the matched candidates, Sheela ranking and candidate score.
NM-HireX owns persistence, history checks, WhatsApp, scheduling and status.
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
    create_job_from_resume_matching_requisition,
    get_admin_job_candidates,
    get_admin_jobs,
    get_job_candidates,
    get_outreach_candidates,
    get_resume_matching_requisitions,
    get_user_dashboard,
    get_user_job_candidates,
    get_user_jobs,
    handle_whatsapp_webhook,
    schedule_candidate_interview,
    send_naukri_outreach_array,
    send_top_outreach,
    sync_resume_matching_candidates,
    update_interview_status,
    update_candidate_status,
    bulk_update_candidate_status,
    get_all_candidates,
    get_pending_outreach_candidates,
    send_pending_outreach_candidates,
)

router = APIRouter(prefix="/api")


# ============================================================
# REQUEST SCHEMAS
# ============================================================
class ScheduleInterviewRequest(BaseModel):
    scheduled_at: datetime
    interview_link: str | None = None


class InterviewStatusRequest(BaseModel):
    status: str

class CandidateStatusRequest(BaseModel):
    status: str
    target_phone: str | None = None


class BulkCandidateStatusRequest(BaseModel):
    candidate_ids: list[UUID]
    status: str = "CONTACTED"
    target_phone: str | None = None


class RequisitionJobRequest(BaseModel):
    vereq_number: str = Field(min_length=1)

class RescheduleRequest(BaseModel):
    new_date: str
    new_time: str
    timezone: str = "UTC"


class NaukriCandidateItem(BaseModel):
    no: int | str | None = None
    name: str
    role: str
    phone: str


class NaukriOutreachRequest(BaseModel):
    job_id: UUID
    candidates: list[NaukriCandidateItem]
    company_name: str | None = None

# ============================================================
# HEALTH
# ============================================================
@router.get("/health")
def health():
    return {"status": "ok", "service": "NM-HireX"}


# ============================================================
# AUTH
# ============================================================
@router.post("/auth/register")
def register(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
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
# WHATSAPP WEBHOOK
# ============================================================
@router.post("/webhooks/whatsapp")
def api_whatsapp_webhook(
    payload: dict,
    x_webhook_secret: str | None = Header(
        default=None,
        alias="X-Webhook-Secret",
    ),
    db: Session = Depends(get_db),
):
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
# INTERVIEW SCHEDULING
# ============================================================
# @router.post("/job-candidates/{job_candidate_id}/schedule")
# def api_schedule_interview(
#     job_candidate_id: UUID,
#     data: ScheduleInterviewRequest,
#     user: User = Depends(get_current_user),
#     db: Session = Depends(get_db),
# ):
#     jc = db.get(JobCandidate, job_candidate_id)
#     if not jc:
#         raise HTTPException(status_code=404, detail="JobCandidate not found")

#     job = db.get(Job, jc.job_id)
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")

#     if user.role != "ADMIN" and job.created_by != user.id:
#         raise HTTPException(status_code=403, detail="Not your job")

#     try:
#         return {
#             "success": True,
#             "data": schedule_candidate_interview(
#                 db=db,
#                 job_candidate_id=job_candidate_id,
#                 scheduled_at=data.scheduled_at,
#                 interview_link=data.interview_link,
#             ),
#         }
#     except ValueError as exc:
#         raise HTTPException(status_code=400, detail=str(exc))


# @router.patch("/job-candidates/{job_candidate_id}/interview-status")
# def api_interview_status(
#     job_candidate_id: UUID,
#     data: InterviewStatusRequest,
#     user: User = Depends(get_current_user),
#     db: Session = Depends(get_db),
# ):
#     jc = db.get(JobCandidate, job_candidate_id)
#     if not jc:
#         raise HTTPException(status_code=404, detail="JobCandidate not found")

#     job = db.get(Job, jc.job_id)
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")

#     if user.role != "ADMIN" and job.created_by != user.id:
#         raise HTTPException(status_code=403, detail="Not your job")

#     try:
#         return {
#             "success": True,
#             "data": update_interview_status(
#                 db=db,
#                 job_candidate_id=job_candidate_id,
#                 status=data.status,
#             ),
#         }
#     except ValueError as exc:
#         raise HTTPException(status_code=400, detail=str(exc))


# ============================================================
# USER / ADMIN VIEWS
# ============================================================
@router.get("/user/jobs")
def api_user_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_jobs(db, user.id)

@router.post("/user/jobs/{job_id}/candidates/{candidate_id}/status")
def api_update_candidate_status(
    job_id: UUID,
    candidate_id: UUID,
    data: CandidateStatusRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
    try:
        return get_user_job_candidates(db, user.id, job_id)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not your job")


@router.get("/admin/jobs")
def api_admin_jobs(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_admin_jobs(db)


@router.get("/admin/jobs/{job_id}/candidates")
def api_admin_candidates(
    job_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return get_admin_job_candidates(db, job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/user/dashboard")
def api_user_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_dashboard(db, user.id)


@router.get("/user/outreach")
def api_user_outreach(
    candidate_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_outreach_candidates(db, user.id, candidate_id=candidate_id)

@router.get("/user/candidates")
def api_user_all_candidates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_all_candidates(db, user.id)

class ScheduleConfirmRequest(BaseModel):
    job_candidate_id: UUID
    interview_date: str
    interview_time: str
    timezone: str = "Asia/Kolkata"


def parse_interview_datetime(date_str: str, time_str: str) -> datetime:
    """Robustly parse date and time strings in various standard formats."""
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
# CANDIDATE OUTREACH API (FOR WEB UI & EXTERNAL SYSTEMS)
# POST /api/outreach/send-array
# POST /api/outreach/invite
# Accepts:
# 1) [{ "name": "Rahul", "role": "Software Engineer", "no": "917439717970" }]
# 2) { "name": "Rahul", "role": "Software Engineer", "no": "917439717970" }
# 3) { "candidates": [...], "company_name": "Acme", "job_id": "..." }
# ============================================================
@router.post("/outreach/send-array")
@router.post("/outreach/invite")
async def api_send_outreach_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Unified candidate outreach endpoint.
    Sends WhatsApp invite template to candidates and stores everything in DB.
    Accessible by UI and external systems alike.
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
    job_candidate_ids: list[UUID]


@router.get("/outreach/pending")
def api_get_pending_outreach(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get candidates in the manual outreach queue (recruitment_status='PENDING_OUTREACH')
    who have not had a WhatsApp outreach message sent yet.
    """
    return get_pending_outreach_candidates(db, user_id=user.id if user else None)


@router.post("/outreach/send-pending")
def api_send_pending_outreach(
    req: SendPendingOutreachRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Send WhatsApp outreach messages to selected candidates from the pending queue.
    """
    try:
        res = send_pending_outreach_candidates(db, req.job_candidate_ids)
        return {"success": True, "data": res}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))



# ============================================================
# WHATSAPP INTEGRATION GATEWAY API ROUTES
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
    """Translates typed GatewayError exceptions into FastAPI HTTPExceptions."""
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
    """API 1: List scheduled interviews with pagination loop (POST)."""
    try:
        return fetch_schedules(filters)
    except Exception as exc:
        _handle_gateway_exception(exc)


@router.get("/gateway/schedules")
def api_get_gateway_schedules(
    page: int = Query(1),
    pageSize: int = Query(50),
    startDate: str | None = Query(None),
    endDate: str | None = Query(None),
    date: str | None = Query(None),
    dateType: str | None = Query("interview_date"),
    is_registered: bool | None = Query(None),
    requisition_id: str | None = Query(None),
    candidate_email: str | None = Query(None),
    added_by_email: str | None = Query(None),
    search: str | None = Query(None),
    all: bool | None = Query(None),
    auto_paginate: bool = Query(True),
):
    """API 1: List scheduled interviews with query parameters (GET)."""
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
    """API 2: Retrieve interview results with pagination loop (POST)."""
    try:
        return fetch_interview_results(filters)
    except Exception as exc:
        _handle_gateway_exception(exc)


@router.get("/gateway/interview-results")
def api_get_gateway_interview_results(
    page: int = Query(1),
    pageSize: int = Query(50),
    startDate: str | None = Query(None),
    endDate: str | None = Query(None),
    date: str | None = Query(None),
    requisition_id: str | None = Query(None),
    candidate_email: str | None = Query(None),
    user_id: str | None = Query(None),
    added_by_email: str | None = Query(None),
    test_type: int | None = Query(None),
    result: str | None = Query(None),
    search: str | None = Query(None),
    all: bool | None = Query(None),
    auto_paginate: bool = Query(True),
):
    """API 2: Retrieve interview results with query parameters (GET)."""
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
    startDate: str | None = Query(None),
    endDate: str | None = Query(None),
    requisition_id: str | None = Query(None),
    search: str | None = Query(None),
):
    """Joins scheduled interviews and interview results (Schedule ID + Requisition ID)."""
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
    """API 3: Create candidate and schedule interview on WhatsApp Gateway (WRITE)."""
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
