"""NM-HireX API routes.

The new recruitment flow starts after the external Resume Matching API has
already produced the matched candidates, Sheela ranking and candidate score.
NM-HireX owns persistence, history checks, WhatsApp, scheduling and status.
"""

from datetime import datetime
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


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "is_active": user.is_active,
    }





# ============================================================
# EXTERNAL RESUME MATCHING API - API 1
# ============================================================
@router.get("/resume-matching/requisitions")
def api_resume_matching_requisitions(
    status: str | None = Query("open"),
    department: str | None = Query(None),
    q: str | None = Query(None),
    # Backward-compatible alias; it is translated to the external API's `q`.
    search: str | None = Query(None, include_in_schema=False),
    period: str | None = Query(None),
    created_from: str | None = Query(None),
    created_to: str | None = Query(None),
    sort: str | None = Query("status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include: str | None = Query(None),
    user: User = Depends(get_current_user),
):
    try:
        effective_q = q or search
        effective_include = include if include in {None, "details"} else None

        return {
            "success": True,
            "data": get_resume_matching_requisitions(
                status=status,
                department=department,
                q=effective_q,
                period=period,
                created_from=created_from,
                created_to=created_to,
                sort=sort,
                limit=limit,
                offset=offset,
                include=effective_include,
                end_user=user.email,
            ),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


# ============================================================
# CREATE A LOCAL JOB FROM ONE VEREQ
# ============================================================
@router.post("/resume-matching/requisitions/{vereq_number}/create-job")
def api_create_job_from_vereq(
    vereq_number: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role == "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Admin cannot create jobs",
        )

    try:
        job = create_job_from_resume_matching_requisition(
            db=db,
            user_id=user.id,
            vereq_number=vereq_number,
            end_user=user.email,
        )
        return {
            "success": True,
            "job_id": str(job.id),
            "vereq_number": vereq_number,
            "title": job.title,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


# ============================================================
# EXTERNAL RESUME MATCHING API - API 2
# This is the point where the score/rank enters NM-HireX.
# ============================================================
@router.post("/jobs/{job_id}/resume-matching")
def api_resume_matching(
    job_id: UUID,
    vereq_number: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if user.role != "ADMIN" and job.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not your job")

    try:
        result = sync_resume_matching_candidates(
            db=db,
            job_id=job_id,
            vereq_number=vereq_number,
            top_n=100,
            poll=True,
            end_user=user.email,
        )
        return {
            "success": True,
            "message": "External matches saved successfully",
            "data": result,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )





# ============================================================
# CANDIDATES
# ============================================================
@router.get("/jobs/{job_id}/candidates")
def api_job_candidates(
    job_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if user.role != "ADMIN" and job.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not your job")

    return {
        "success": True,
        "data": get_job_candidates(db, job_id, limit=limit),
    }


# ============================================================
# TOP 50 -> HISTORY CHECK -> WHATSAPP
# ============================================================
@router.post("/jobs/{job_id}/outreach")
def api_outreach(
    job_id: UUID,
    limit: int = Query(50, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if user.role != "ADMIN" and job.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not your job")

    return send_top_outreach(
        db=db,
        job_id=job_id,
        limit=limit,
    )


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
@router.post("/job-candidates/{job_candidate_id}/schedule")
def api_schedule_interview(
    job_candidate_id: UUID,
    data: ScheduleInterviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jc = db.get(JobCandidate, job_candidate_id)
    if not jc:
        raise HTTPException(status_code=404, detail="JobCandidate not found")

    job = db.get(Job, jc.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if user.role != "ADMIN" and job.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not your job")

    try:
        return {
            "success": True,
            "data": schedule_candidate_interview(
                db=db,
                job_candidate_id=job_candidate_id,
                scheduled_at=data.scheduled_at,
                interview_link=data.interview_link,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/job-candidates/{job_candidate_id}/interview-status")
def api_interview_status(
    job_candidate_id: UUID,
    data: InterviewStatusRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jc = db.get(JobCandidate, job_candidate_id)
    if not jc:
        raise HTTPException(status_code=404, detail="JobCandidate not found")

    job = db.get(Job, jc.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if user.role != "ADMIN" and job.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not your job")

    try:
        return {
            "success": True,
            "data": update_interview_status(
                db=db,
                job_candidate_id=job_candidate_id,
                status=data.status,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
def api_scheduling_dates():
    import datetime
    today = datetime.date.today()
    dates = []
    # Provide next 7 days starting from today (24h round-the-clock availability)
    for i in range(0, 8):
        d = today + datetime.timedelta(days=i)
        dates.append({"date": d.isoformat()})
    return {"dates": dates}


@router.get("/scheduling/slots")
def api_scheduling_slots(date: str | None = None):
    # Available for 24 hours round-the-clock (every 30 mins)
    slots = []
    for hour in range(24):
        for minute in (0, 30):
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
    from .tools_function import schedule_candidate_interview
    
    dt = parse_interview_datetime(req.interview_date, req.interview_time)
    teams_link = f"https://teams.microsoft.com/l/meetup-join/nmhirex-{req.job_candidate_id}"
    
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
    from .models import JobCandidate
    from .tools_function import schedule_candidate_interview
    
    jc = db.query(JobCandidate).filter(JobCandidate.reschedule_token == token).first()
    if not jc:
        raise HTTPException(
            status_code=404,
            detail="This reschedule link has already been used or is expired. Interviews can only be rescheduled once."
        )
        
    dt = parse_interview_datetime(req.new_date, req.new_time)
    
    teams_link = jc.interview_link or f"https://teams.microsoft.com/l/meetup-join/nmhirex-{jc.id}"
    
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

    if isinstance(body, list):
        candidates_list = body
    elif isinstance(body, dict):
        if "candidates" in body and isinstance(body["candidates"], list):
            candidates_list = body["candidates"]
            job_id = body.get("job_id")
            company_name = body.get("company_name")
        elif "name" in body and ("phone" in body or "no" in body or "phone_number" in body or "mobile" in body):
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
        )
        return {"success": True, "data": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))

