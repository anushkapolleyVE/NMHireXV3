"""All actual NM-HireX business functions.

Each function is intentionally small and directly composable; LangGraph is not
required for this deterministic pipeline.
"""
import json
import logging
import os
import random
import re
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    User,
    Job,
    Candidate,
    JobCandidate,
    CandidateContact,
)

WHATSAPP_STAGE_NUMBERS = [
    "919883236730",
    "919064148052",
    "917439717970",
    "919330609485",
]


# ------------------------------------------------------------
# QUERY FUNCTIONS
# ------------------------------------------------------------
def get_job_candidates(
    db: Session,
    job_id: UUID,
    limit: int = 10,
) -> list[dict]:
    """
    Return ranked candidates for a job.

    The external Resume Matching API score stored in JobCandidate.overall_score
    is the primary score. If an older NM-HireX ScreeningResult exists, its
    breakdown is returned for backward compatibility, but it is not required.
    """
    rows = db.execute(
        select(JobCandidate, Candidate)
        .join(
            Candidate,
            Candidate.id == JobCandidate.candidate_id,
        )
        .where(
            JobCandidate.job_id == job_id,
            JobCandidate.is_shortlisted.is_(True),
        )
        .order_by(
            JobCandidate.ranking_position.asc()
        )
    ).all()

    candidate_ids = [
        candidate.id
        for _, candidate in rows[:limit]
    ]

    resumes = {}
    if candidate_ids:
        all_resumes = db.execute(
            select(Resume)
            .where(Resume.candidate_id.in_(candidate_ids))
            .order_by(Resume.uploaded_at.desc())
        ).scalars().all()

        for resume in all_resumes:
            if resume.candidate_id not in resumes:
                resumes[resume.candidate_id] = resume

    # Load old detailed screening records only when they exist.
    screening_map = {}
    jc_ids = [
        jc.id
        for jc, _ in rows[:limit]
    ]

    if jc_ids:
        screenings = db.execute(
            select(ScreeningResult)
            .where(
                ScreeningResult.job_candidate_id.in_(jc_ids)
            )
        ).scalars().all()

        screening_map = {
            screening.job_candidate_id: screening
            for screening in screenings
        }

    results = []

    for jc, candidate in rows[:limit]:
        screening = screening_map.get(jc.id)

        external_score = (
            float(jc.overall_score)
            if jc.overall_score is not None
            else None
        )

        score = (
            external_score
            if external_score is not None
            else (
                float(screening.total_score)
                if screening and screening.total_score is not None
                else 0
            )
        )

        classification = (
            jc.classification
            or (
                screening.classification
                if screening
                else None
            )
            or "External Match"
        )

        score_breakdown = None

        if screening:
            mandatory = float(screening.mandatory_skills_score or 0)
            experience = float(screening.experience_score or 0)
            domain = float(screening.domain_score or 0)
            preferred = float(screening.preferred_skills_score or 0)
            education = float(screening.education_score or 0)
            location = float(screening.location_score or 0)
            availability = float(screening.availability_score or 0)
            other = float(screening.other_requirements_score or 0)

            score_breakdown = {
                "mandatory_skills": {
                    "score": mandatory,
                    "max_score": 30,
                    "percentage": round((mandatory / 30) * 100),
                },
                "experience": {
                    "score": experience,
                    "max_score": 25,
                    "percentage": round((experience / 25) * 100),
                },
                "domain": {
                    "score": domain,
                    "max_score": 15,
                    "percentage": round((domain / 15) * 100),
                },
                "preferred_skills": {
                    "score": preferred,
                    "max_score": 10,
                    "percentage": round((preferred / 10) * 100),
                },
                "education": {
                    "score": education,
                    "max_score": 5,
                    "percentage": round((education / 5) * 100),
                },
                "location": {
                    "score": location,
                    "max_score": 5,
                    "percentage": round((location / 5) * 100),
                },
                "availability": {
                    "score": availability,
                    "max_score": 5,
                    "percentage": round((availability / 5) * 100),
                },
                "other_requirements": {
                    "score": other,
                    "max_score": 5,
                    "percentage": round((other / 5) * 100),
                },
            }
        else:
            score_breakdown = {
                "external_match_score": {
                    "score": score,
                    "max_score": 100,
                    "percentage": score,
                }
            }

        reasoning = None
        if screening and screening.matching_details:
            reasoning = screening.matching_details.get(
                "evaluation"
            )

        resume = resumes.get(candidate.id)

        results.append({
            "rank": jc.ranking_position,
            "candidate_id": str(candidate.id),
            "job_candidate_id": str(jc.id),
            "name": candidate.name,
            "email": candidate.email,
            "phone": candidate.phone,
            "resume_url": (
                resume.file_url
                if resume
                else None
            ),
            "experience_years": (
                float(candidate.total_experience_years)
                if candidate.total_experience_years is not None
                else None
            ),
            "current_company": candidate.current_company,
            "current_role": candidate.current_role,
            "location": candidate.location,
            "notice_period_days": candidate.notice_period_days,
            "skills": (
                candidate.normalized_profile.get("skills", [])
                if candidate.normalized_profile
                else []
            ),
            "experience_details": (
                candidate.normalized_profile.get("experiences", [])
                if candidate.normalized_profile
                else []
            ),
            "score": score,
            "external_score": external_score,
            "classification": classification,
            "status": jc.recruitment_status,
            "score_breakdown": score_breakdown,
            "reasoning": reasoning,
        })

    return results

def get_user_jobs(db: Session, user_id: UUID) -> list[dict]:
    """Input: authenticated user UUID. Output: only that user's JDs."""
    jobs = db.scalars(select(Job).where(Job.created_by == user_id).order_by(Job.created_at.desc())).all()
    return [{"job_id": str(j.id), "id": str(j.id), "title": j.title, "description": j.description, "location": j.location, "work_mode": j.work_mode, "file_name": None, "status": j.status,
             "created_at": j.created_at.isoformat() if j.created_at else None} for j in jobs]

def get_user_job_candidates(db: Session, user_id: UUID, job_id: UUID) -> list[dict]:
    """Input: authenticated user and job UUID. Output: Top 10 only when the user owns the JD."""
    if not db.scalar(select(Job.id).where(Job.id == job_id, Job.created_by == user_id)):
        raise PermissionError("Job does not belong to current user")
    return get_job_candidates(db, job_id, limit=50)

def get_admin_jobs(db: Session) -> list[dict]:
    """Input: DB session. Output: all JDs with uploader and Top 10 summary."""
    rows = db.execute(select(Job, User).join(User, User.id == Job.created_by).order_by(Job.created_at.desc())).all()
    return [{"job_id": str(j.id), "title": j.title, "file_name": None, "status": j.status,
             "uploaded_by": {"id": str(u.id), "name": u.name, "email": u.email},
             "top_10": get_job_candidates(db, j.id)} for j, u in rows]

def get_admin_job_candidates(db: Session, job_id: UUID) -> list[dict]:
    """Input: job UUID. Output: Top 10 persisted candidates for that JD."""
    if not db.get(Job, job_id):
        raise ValueError("Job not found")
    return get_job_candidates(db, job_id)

def get_user_dashboard(db: Session, user_id: UUID) -> dict:
    """Input: user UUID. Output: WhatsApp outreach stats and recent candidates."""
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    q = (
        select(JobCandidate, Candidate, Job)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
        .join(Job, Job.id == JobCandidate.job_id)
    )

    all_jc = db.execute(q.order_by(JobCandidate.updated_at.desc())).all()

    invites_sent = 0
    interested = 0
    meeting_scheduled = 0
    not_interested = 0
    awaiting = 0
    delivered_count = 0
    failed_count = 0
    skipped_count = 0

    recent_candidates = []

    for jc, cand, job in all_jc:
        status = jc.recruitment_status or "NEW"
        has_outreach = status in {
            "CONTACTED",
            "INTERESTED",
            "INTERVIEW_LINK_SENT",
            "INTERVIEW_SCHEDULED",
            "INTERVIEW",
            "INTERVIEW_COMPLETED",
            "NOT_INTERESTED",
            "SKIPPED",
            "INVALID_PHONE",
            "SKIPPED_INVALID_PHONE",
            "FAILED",
        }

        if has_outreach:
            # Determine delivery status from latest outbound contact log FIRST
            latest_contact = db.scalar(
                select(CandidateContact)
                .where(
                    CandidateContact.job_candidate_id == jc.id,
                    CandidateContact.message_type == "OUTBOUND",
                )
                .order_by(CandidateContact.created_at.desc())
                .limit(1)
            )

            c_status = (latest_contact.status if latest_contact else ("DELIVERED" if status in {"INTERESTED", "INTERVIEW_LINK_SENT", "INTERVIEW_SCHEDULED"} else "DELIVERED")).upper()
            if c_status in {"INVALID_PHONE", "SKIPPED", "SKIPPED_INVALID_PHONE"} or status in {"SKIPPED", "INVALID_PHONE", "SKIPPED_INVALID_PHONE"}:
                delivery_status = "INVALID_PHONE"
                display_status = "SKIPPED"
                skipped_count += 1
            elif c_status == "FAILED" or status == "FAILED":
                delivery_status = "FAILED"
                display_status = "FAILED"
                failed_count += 1
            else:
                # Any outreach message successfully sent is DELIVERED and increments delivered_count
                delivery_status = "DELIVERED"
                display_status = status
                delivered_count += 1

            if status not in {"SKIPPED", "INVALID_PHONE", "SKIPPED_INVALID_PHONE"}:
                invites_sent += 1

            if status in {"INTERVIEW_SCHEDULED", "INTERVIEW", "INTERVIEW_COMPLETED"} or jc.interview_scheduled_at is not None:
                meeting_scheduled += 1
                interested += 1
            elif status in {"INTERESTED", "INTERVIEW_LINK_SENT"}:
                interested += 1
            elif status == "NOT_INTERESTED":
                not_interested += 1
            elif status == "CONTACTED":
                # Only count as awaiting reply if the outreach message did NOT fail to send/deliver
                if delivery_status not in {"FAILED", "INVALID_PHONE"}:
                    awaiting += 1

            if len(recent_candidates) < 40:
                scheduled_str = (
                    jc.interview_scheduled_at.strftime("%Y-%m-%dT%H:%M:%S")
                    if jc.interview_scheduled_at
                    else None
                )
                recent_candidates.append({
                    "id": str(cand.id),
                    "job_candidate_id": str(jc.id),
                    "job_id": str(job.id),
                    "name": cand.name or "Unnamed",
                    "role": cand.current_role or job.title or "Position",
                    "phone": cand.phone or "",
                    "status": display_status,
                    "delivery_status": delivery_status,
                    "interview_scheduled_at": scheduled_str,
                    "interview_link": jc.interview_link,
                    "updated_at": jc.updated_at.isoformat() if jc.updated_at else None,
                })

    return {
        "user_name": user.name,
        "metrics": {
            "invites_sent": invites_sent,
            "interested": interested,
            "meeting_scheduled": meeting_scheduled,
            "not_interested": not_interested,
            "awaiting": awaiting,
            "delivered": delivered_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "invalid_phone": skipped_count,
            "total_outreach": delivered_count + failed_count + skipped_count,
            "delivery_rate": (
                round((delivered_count / (delivered_count + failed_count + skipped_count)) * 100)
                if (delivered_count + failed_count + skipped_count) > 0
                else 100
            ),
            "active_jobs": invites_sent,
            "candidates_screened": invites_sent,
            "strong_matches": interested,
            "whatsapp_outreach": invites_sent,
        },
        "recent_candidates": recent_candidates,
        "pipeline": recent_candidates,
    }


def _clean_whatsapp_phone(raw_phone: str | None) -> str:
    """Normalize and strictly validate an Indian WhatsApp number.

    A valid Indian mobile number must have 10 mobile digits starting with 6, 7, 8, or 9:
    - If 12 digits starting with country code 91 and clean[2] in '6789': return clean_phone
    - If 10 digits starting with '6789' (and NOT starting with 91): return '91' + clean_phone
    - If starting with 91 but total length is not 12 (e.g. 8, 9, 10, or 11 digits): REJECT (return "")
    - Any other format, length, or prefix: REJECT (return "")
    """
    if not raw_phone:
        return ""

    clean_phone = "".join(filter(str.isdigit, str(raw_phone)))

    # Strip leading 0 if present (e.g. 0XXXXXXXXXX or 091XXXXXXXXXX)
    if clean_phone.startswith("0"):
        clean_phone = clean_phone.lstrip("0")

    # If it starts with country code 91:
    if clean_phone.startswith("91"):
        # Must be exactly 12 digits, and the mobile number (digits after 91) must start with 6, 7, 8, or 9
        if len(clean_phone) == 12 and clean_phone[2] in "6789":
            return clean_phone
        # If it starts with 91 but does not have exactly 10 digits after 91 (e.g. 91 + 8 digits = 10 digits),
        # it is an incomplete number and must NOT have another 91 prepended.
        return ""

    # If without country code 91:
    # Must be exactly 10 digits and start with 6, 7, 8, or 9
    if len(clean_phone) == 10 and clean_phone[0] in "6789":
        return "91" + clean_phone

    # Invalid phone length or format
    return ""


def _whatsapp_headers() -> dict:
    """Build NMVE WhatsApp headers from server-side configuration."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    api_key = (
        getattr(settings, "WHATSAPP_MESSAGE_API_KEY", "")
        or getattr(settings, "WHATSAPP_API_KEY", "")
        or os.getenv("WHATSAPP_MESSAGE_API_KEY", "")
        or os.getenv("WHATSAPP_API_KEY", "")
    )
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["api-key"] = api_key

    return headers


def _extract_provider_message_id(response_body: str | dict | None) -> str | None:
    """Extract a provider message ID without assuming one fixed NMVE response shape."""
    if isinstance(response_body, dict):
        for key in (
            "messageId",
            "message_id",
            "externalMessageId",
            "external_message_id",
            "id",
        ):
            value = response_body.get(key)
            if value:
                return str(value)

        for nested_key in ("data", "result", "message"):
            nested = response_body.get(nested_key)
            if isinstance(nested, dict):
                nested_id = _extract_provider_message_id(nested)
                if nested_id:
                    return nested_id

    return None


def _send_whatsapp_payload(
    payload: dict,
) -> tuple[bool, dict | None, str | None]:
    """
    Send a WhatsApp payload to NMVE.

    In test mode, the destination is ALWAYS
    WHATSAPP_TEST_NUMBER.

    If test mode is enabled but the test number is missing,
    the message is blocked to prevent accidental delivery
    to a real candidate.
    """

    base_url = getattr(
        settings,
        "WHATSAPP_BASE_URL",
        "https://nmve.io/whatsapp/api/integrations/whatsapp/template-messages",
    )

    # Text messages (CTA scheduling link, meeting link) MUST go to /messages.
    # NMVE rejects text messages at /template-messages with validation error.
    if payload.get("type") == "text" or "templateName" not in payload:
        url = base_url.replace("/template-messages", "/messages")
    else:
        url = base_url

    api_key = (
        getattr(settings, "WHATSAPP_MESSAGE_API_KEY", "")
        or getattr(settings, "WHATSAPP_API_KEY", "")
        or os.getenv("WHATSAPP_MESSAGE_API_KEY", "")
        or os.getenv("WHATSAPP_API_KEY", "")
    )

    if not api_key:
        print(
            "WHATSAPP_MESSAGE_API_KEY (or WHATSAPP_API_KEY) is not configured for sending messages."
        )
        return False, None, None

    # --------------------------------------------------
    # WHATSAPP TEST MODE SAFETY OVERRIDE
    # --------------------------------------------------

    if getattr(
        settings,
        "WHATSAPP_TEST_MODE",
        False,
    ):

        test_number = getattr(
            settings,
            "WHATSAPP_TEST_NUMBER",
            "",
        )

        if not test_number:
            print(
                "WHATSAPP TEST MODE is enabled but "
                "WHATSAPP_TEST_NUMBER is missing. "
                "BLOCKING WhatsApp send."
            )
            return False, None, None

        test_phone = _clean_whatsapp_phone(
            test_number
        )

        if not test_phone:
            print(
                "WHATSAPP_TEST_NUMBER is invalid. "
                "BLOCKING WhatsApp send."
            )
            return False, None, None

        original_to = payload.get("to")

        payload["to"] = test_phone

        print(
            f"WHATSAPP TEST MODE: "
            f"{original_to} -> {test_phone}"
        )

    # --------------------------------------------------
    # SEND PAYLOAD
    # --------------------------------------------------

    data = json.dumps(payload).encode(
        "utf-8"
    )

    headers = _whatsapp_headers()
    print(f"[WhatsApp] Sending to {payload.get('to')} using messaging key: {api_key[:14]}... on {url}")

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:

            body = response.read().decode(
                "utf-8",
                errors="replace",
            )

            print(
                f"WhatsApp API response status: "
                f"{response.status}"
            )

            parsed = None

            if body.strip():
                try:
                    parsed = json.loads(body)

                except json.JSONDecodeError:
                    parsed = {
                        "raw_response": body
                    }

            return (
                True,
                parsed,
                _extract_provider_message_id(
                    parsed
                ),
            )

    except urllib.error.HTTPError as http_err:

        try:
            error_body = (
                http_err.read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )

        except Exception:
            error_body = str(
                http_err
            )

        print(
            f"WhatsApp API HTTP Error: "
            f"{http_err.code}"
        )

        print(
            f"Error Details: "
            f"{error_body}"
        )

        return False, None, None

    except Exception as error:

        print(
            f"WhatsApp API Error: "
            f"{error}"
        )

        return False, None, None


def _send_whatsapp_to_candidate(
    db: Session,
    job_id: UUID,
    candidate_id: UUID,
    target_phone: str | None = None,
):
    """
    Send the initial NMVE WhatsApp template to one candidate.

    TEST MODE:
        WHATSAPP_TEST_NUMBER is ALWAYS used.

    NORMAL MODE:
        target_phone -> WHATSAPP_STAGE_NUMBER -> candidate.phone

    The function records the successful outbound message in
    candidate_contacts and moves a NEW candidate to CONTACTED.
    No candidate score is calculated here.
    """

    print(
        f"--- Attempting WhatsApp Integration for candidate "
        f"{candidate_id} ---"
    )

    try:
        candidate = db.query(Candidate).filter(
            Candidate.id == candidate_id
        ).first()

        if not candidate:
            print(
                "Candidate not found in DB."
            )
            return False

        job_candidate = db.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == job_id,
                JobCandidate.candidate_id == candidate_id,
            )
        )

        if not job_candidate:
            print(
                "JobCandidate not found."
            )
            return False

        # --------------------------------------------------
        # PHONE NUMBER
        # --------------------------------------------------

        if getattr(
            settings,
            "WHATSAPP_TEST_MODE",
            False,
        ):

            # --------------------------------------------------
            # TEST MODE
            # NEVER USE CANDIDATE PHONE
            # --------------------------------------------------

            test_number = getattr(
                settings,
                "WHATSAPP_TEST_NUMBER",
                "",
            )

            if not test_number:
                print(
                    "WHATSAPP TEST MODE is enabled but "
                    "WHATSAPP_TEST_NUMBER is not configured. "
                    "Blocking WhatsApp send."
                )
                return False

            clean_phone = _clean_whatsapp_phone(
                test_number
            )

            if not clean_phone:
                print(
                    "WHATSAPP_TEST_NUMBER is invalid. "
                    "Blocking WhatsApp send."
                )
                return False

            print(
                f"WHATSAPP TEST MODE ENABLED - "
                f"Sending ONLY to test number: "
                f"{clean_phone}"
            )

        else:

            # --------------------------------------------------
            # NORMAL PRODUCTION MODE
            # EXISTING PHONE PRIORITY
            # --------------------------------------------------

            # raw_phone = target_phone

            # if not raw_phone:
            #     raw_phone = getattr(
            #         settings,
            #         "WHATSAPP_STAGE_NUMBER",
            #         None,
            #     )

            # if not raw_phone:
            #     raw_phone = (
            #         str(candidate.phone)
            #         if candidate.phone
            #         else ""
            #     )

            raw_phone = target_phone

            if not raw_phone:
                if WHATSAPP_STAGE_NUMBERS:
                    random_index = random.randint(
                        0, len(WHATSAPP_STAGE_NUMBERS) - 1
                    )
                    raw_phone = WHATSAPP_STAGE_NUMBERS[random_index]
                else:
                    raw_phone = (
                        str(candidate.phone)
                        if candidate.phone
                        else ""
                    )


            clean_phone = _clean_whatsapp_phone(
                raw_phone
            )

            if not clean_phone:
                print(
                    "No valid phone number available "
                    "for candidate. "
                    "Skipping WhatsApp."
                )
                return False

        # --------------------------------------------------
        # CONFIGURATION
        # --------------------------------------------------

        callback_url = getattr(
            settings,
            "WHATSAPP_CALLBACK_URL",
            "https://nmhirexv3.onrender.com/api/webhooks/whatsapp",
        )

        template_name = getattr(
            settings,
            "WHATSAPP_TEMPLATE_NAME",
            "hello_world",
        )

        template_language = getattr(
            settings,
            "WHATSAPP_TEMPLATE_LANGUAGE",
            "en_US",
        )

        reference_id = (
            f"NMHireX-{str(job_candidate.id)}"
        )

        # --------------------------------------------------
        # WHATSAPP PAYLOAD
        # --------------------------------------------------

        # Fetch the job title and company name for template body params
        job = db.get(Job, job_id)
        job_title = (job.title if job else None) or "the position"
        company_name = getattr(settings, "WHATSAPP_COMPANY_NAME", "the company")

        # Build the template payload with bodyParams for candidate_shortlisted_outreach
        # bodyParams: [candidate_name, role, company (1st), company (2nd)]
        payload = {
            "to": clean_phone,
            "templateName": template_name,
            "bodyParams": [
                candidate.name or "Candidate",
                job_title,
                company_name,
                company_name,
            ],
            "languageCode": template_language,
            "referenceId": reference_id,
            "callbackUrl": callback_url,
        }

        print(
            f"Sending WhatsApp payload to "
            f"{clean_phone}..."
        )

        success, response_body, provider_message_id = (
            _send_whatsapp_payload(
                payload
            )
        )

        if not success:
            return False

        # --------------------------------------------------
        # SAVE OUTBOUND MESSAGE
        # --------------------------------------------------

        contact = CandidateContact(
            job_candidate_id=job_candidate.id,
            channel="WHATSAPP",
            message_type="OUTBOUND",
            message="Hi",
            provider="NMVE",
            external_message_id=provider_message_id,
            status="SENT",
            sent_at=datetime.utcnow(),
        )

        db.add(contact)

        # --------------------------------------------------
        # UPDATE RECRUITMENT STATUS
        # --------------------------------------------------

        if job_candidate.recruitment_status in {
            None,
            "NEW",
            "SHORTLISTED",
        }:
            job_candidate.recruitment_status = (
                "CONTACTED"
            )

        db.commit()

        print(
            "WhatsApp message saved to "
            "candidate_contacts."
        )

        return True

    except Exception as error:

        db.rollback()

        print(
            f"Error in WhatsApp integration: "
            f"{error}"
        )

        return False


def _send_whatsapp_text_message(
    raw_phone: str,
    text_message: str,
):
    """
    Send a plain-text WhatsApp message through NMVE.
    """

    try:

        clean_phone = _clean_whatsapp_phone(
            raw_phone
        )

        if not clean_phone:
            print(
                "No valid phone number supplied."
            )
            return False

        payload = {
            "to": clean_phone,
            "type": "text",
            "text": {
                "body": text_message,
                "preview_url": True,
            },
        }

        success, _, _ = _send_whatsapp_payload(
            payload
        )

        if success:
            print(
                f"WhatsApp text message sent to "
                f"{clean_phone}."
            )

        return success

    except Exception as error:

        print(
            f"Error sending WhatsApp text: "
            f"{error}"
        )

        return False


def _send_whatsapp_cta_message(
    raw_phone: str,
    job_candidate_id: str,
):
    """
    Send the interview scheduling CTA,
    with text fallback.
    """

    clean_phone = _clean_whatsapp_phone(
        raw_phone
    )

    if not clean_phone:
        print(
            "No valid phone number supplied."
        )
        return False

    frontend_url = getattr(
        settings,
        "FRONTEND_URL",
        "https://nm-hire-xv-3-c4m5.vercel.app",
    ).rstrip("/")

    # WhatsApp candidates cannot access localhost; always use public Vercel domain
    if not frontend_url or "localhost" in frontend_url or "127.0.0.1" in frontend_url:
        frontend_url = "https://nm-hire-xv-3-c4m5.vercel.app"

    scheduling_link = (
        f"{frontend_url}/schedule/{job_candidate_id}"
    )

    text_message = (
        "Great news! 🎉 We'd love to move forward with your application.\n\n"
        "Please select your preferred date and time for the interview using the link below:\n\n"
        f"{scheduling_link}\n\n"
        "💡 *Note:* If the link above is not clickable, please save this number to your contacts or tap 'Add to contacts' at the top of the chat.\n\n"
        "We look forward to connecting with you! 😊"
    )

    return _send_whatsapp_text_message(
        clean_phone,
        text_message,
    )





def _candidate_has_contact_history(
    db: Session,
    job_candidate_id: UUID,
) -> bool:
    """Return True when WhatsApp/email/SMS contact already exists for this requisition."""
    return db.scalar(
        select(CandidateContact.id)
        .where(
            CandidateContact.job_candidate_id == job_candidate_id
        )
        .limit(1)
    ) is not None



def _classify_whatsapp_response(message: str) -> str:
    """Simple deterministic YES/NO classifier for recruitment responses."""
    text_value = (message or "").strip().lower()

    negative_patterns = [
        r"\bnot interested\b",
        r"\bno thanks\b",
        r"\bdo not want\b",
        r"\bdon't want\b",
        r"\bdecline\b",
        r"\bnot looking\b",
        r"\bno\b",
    ]

    for pattern in negative_patterns:
        if re.search(pattern, text_value):
            return "NOT_INTERESTED"

    positive_patterns = [
        r"\byes\b",
        r"\binterested\b",
        r"\bsure\b",
        r"\bok\b",
        r"\bokay\b",
        r"\bproceed\b",
        r"\binterview\b",
        r"\bschedule\b",
    ]

    for pattern in positive_patterns:
        if re.search(pattern, text_value):
            return "INTERESTED"

    return "UNKNOWN"


def handle_whatsapp_webhook(
    db: Session,
    payload: dict,
) -> dict:
    """Process an inbound NMVE WhatsApp webhook and advance the recruitment workflow."""

    def find_value(data, keys):
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, (str, int, float)) and str(value).strip():
                    return str(value).strip()
            for nested in data.values():
                result = find_value(nested, keys)
                if result:
                    return result
        elif isinstance(data, list):
            for nested in data:
                result = find_value(nested, keys)
                if result:
                    return result
        return None

    phone = _clean_whatsapp_phone(
        find_value(
            payload,
            ["to", "from", "phone", "sender", "wa_id", "waId", "phoneNumber", "fromNumber", "recipient_id"],
        )
    )

    text_message = find_value(
        payload,
        [
            "text",
            "body",
            "messageText",
            "content",
            "button_text",
            "buttonText",
            "title",
            "button_payload",
            "buttonPayload",
            "selectedId",
        ],
    ) or ""

    reference_id = find_value(
        payload,
        ["referenceId", "reference_id", "reference"],
    )

    provider_message_id = find_value(
        payload,
        ["messageId", "message_id", "externalMessageId", "external_message_id", "id"],
    )

    if not phone and not reference_id:
        return {
            "status": "IGNORED",
            "reason": "Missing phone and reference ID",
        }

    # Update CandidateContact on delivery status receipts (e.g. delivered, failed, read, sent)
    if not text_message or not text_message.strip():
        data_dict = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        status_val = (
            data_dict.get("status")
            or data_dict.get("deliveryStatus")
            or data_dict.get("messageStatus")
            or data_dict.get("delivery_status")
            or payload.get("deliveryStatus")
            or payload.get("messageStatus")
            or ("failed" if (data_dict.get("errorCode") or data_dict.get("errorMessage") or payload.get("errorCode")) else None)
        )
        if not status_val and isinstance(payload.get("eventId"), str):
            eid = payload.get("eventId").lower()
            if ":failed" in eid:
                status_val = "failed"
            elif ":delivered" in eid:
                status_val = "delivered"
            elif ":sent" in eid:
                status_val = "sent"

        if status_val:
            status_clean = str(status_val).strip().upper()
            target_contact = None
            if provider_message_id:
                target_contact = db.scalar(
                    select(CandidateContact)
                    .where(CandidateContact.external_message_id == provider_message_id)
                    .limit(1)
                )
            if not target_contact and reference_id and reference_id.startswith("NMHireX-"):
                ref_jc_id = reference_id.replace("NMHireX-", "").strip()
                try:
                    target_contact = db.scalar(
                        select(CandidateContact)
                        .where(
                            CandidateContact.job_candidate_id == UUID(ref_jc_id),
                            CandidateContact.message_type == "OUTBOUND",
                        )
                        .order_by(CandidateContact.created_at.desc())
                        .limit(1)
                    )
                except (ValueError, TypeError):
                    target_contact = None
            if not target_contact and phone:
                raw_digits = "".join(filter(str.isdigit, phone))
                target_contact = db.scalar(
                    select(CandidateContact)
                    .join(JobCandidate, JobCandidate.id == CandidateContact.job_candidate_id)
                    .join(Candidate, Candidate.id == JobCandidate.candidate_id)
                    .where(
                        (Candidate.phone == phone) | 
                        (Candidate.phone == raw_digits) | 
                        ((Candidate.phone.like(f"%{raw_digits[-10:]}")) if len(raw_digits) >= 10 else (Candidate.phone == phone)),
                        CandidateContact.message_type == "OUTBOUND"
                    )
                    .order_by(CandidateContact.created_at.desc())
                    .limit(1)
                )
            if target_contact:
                if "DELIVER" in status_clean:
                    target_contact.status = "DELIVERED"
                    target_contact.delivered_at = datetime.utcnow()
                elif "FAIL" in status_clean or "UNDELIVER" in status_clean or data_dict.get("errorCode"):
                    target_contact.status = "FAILED"
                    err_msg = data_dict.get("errorMessage") or data_dict.get("error") or find_value(payload, ["errorMessage", "error", "error_message", "reason"]) or "Delivery failed"
                    target_contact.message = f"Failed: {err_msg}"
                    jc_rec = db.get(JobCandidate, target_contact.job_candidate_id)
                    if jc_rec and jc_rec.recruitment_status in {None, "NEW", "CONTACTED"}:
                        jc_rec.recruitment_status = "FAILED"
                elif "READ" in status_clean:
                    target_contact.status = "READ"
                    target_contact.read_at = datetime.utcnow()
                elif "SENT" in status_clean:
                    target_contact.status = "SENT"
                    target_contact.sent_at = target_contact.sent_at or datetime.utcnow()
                db.commit()
                print(f"WEBHOOK: Updated delivery status of contact {target_contact.id} to {target_contact.status}")
                return {
                    "status": "STATUS_UPDATED",
                    "delivery_status": target_contact.status,
                }
            elif reference_id and reference_id.startswith("NMHireX-"):
                ref_jc_id = reference_id.replace("NMHireX-", "").strip()
                try:
                    jc_uuid = UUID(ref_jc_id)
                    if db.get(JobCandidate, jc_uuid):
                        err_msg = data_dict.get("errorMessage") or find_value(payload, ["errorMessage", "error", "error_message"]) or "Delivery failed"
                        is_failed = "FAIL" in status_clean or "UNDELIVER" in status_clean or data_dict.get("errorCode")
                        is_delivered = "DELIVER" in status_clean
                        new_contact = CandidateContact(
                            job_candidate_id=jc_uuid,
                            channel="WHATSAPP",
                            message_type="OUTBOUND",
                            message=f"Failed: {err_msg}" if is_failed else "Candidate outreach invitation",
                            provider="NMVE",
                            external_message_id=provider_message_id,
                            status="FAILED" if is_failed else ("DELIVERED" if is_delivered else "SENT"),
                            sent_at=datetime.utcnow(),
                            delivered_at=datetime.utcnow() if is_delivered else None,
                        )
                        db.add(new_contact)
                        if is_failed:
                            target_jc = db.get(JobCandidate, jc_uuid)
                            if target_jc and target_jc.recruitment_status in {None, "NEW", "CONTACTED"}:
                                target_jc.recruitment_status = "FAILED"
                        db.commit()
                        print(f"WEBHOOK: Created contact for {jc_uuid} with status {new_contact.status}")
                        return {
                            "status": "STATUS_CREATED",
                            "delivery_status": new_contact.status,
                        }
                    else:
                        print(f"WEBHOOK: JobCandidate {jc_uuid} not found in DB. Skipping contact creation.")
                except (ValueError, TypeError):
                    pass

        print(f"WEBHOOK: Delivery status or empty message received from {phone} (ignoring).")
        return {
            "status": "IGNORED",
            "reason": "Empty message body or delivery status receipt",
        }

    # First try the reference ID generated by NM-HireX.
    job_candidate = None
    if reference_id:
        candidate_prefix = "NMHireX-"
        if reference_id.startswith(candidate_prefix):
            candidate_job_id = reference_id[len(candidate_prefix):]
            try:
                job_candidate = db.get(JobCandidate, UUID(candidate_job_id))
            except (ValueError, TypeError):
                job_candidate = None

    print(f"WEBHOOK EXTRACTED PHONE: {phone}")
    print(f"WEBHOOK EXTRACTED TEXT: {text_message}")

    # Fall back to the latest active candidate record for the phone number.
    if job_candidate is None and phone:
        job_candidate = db.execute(
            select(JobCandidate)
            .join(Candidate, Candidate.id == JobCandidate.candidate_id)
            .where(
                Candidate.phone == phone,
                JobCandidate.recruitment_status.in_([
                    "CONTACTED",
                    "INTERESTED",
                    "INTERVIEW_LINK_SENT",
                ]),
            )
            .order_by(JobCandidate.updated_at.desc())
        ).scalars().first()
        
        if not job_candidate and phone.startswith("91"):
            alt_phone = phone[2:]
            print(f"WEBHOOK: Try fallback without country code: {alt_phone}")
            job_candidate = db.execute(
                select(JobCandidate)
                .join(Candidate, Candidate.id == JobCandidate.candidate_id)
                .where(
                    Candidate.phone == alt_phone,
                    JobCandidate.recruitment_status.in_([
                        "CONTACTED",
                        "INTERESTED",
                        "INTERVIEW_LINK_SENT",
                    ]),
                )
                .order_by(JobCandidate.updated_at.desc())
            ).scalars().first()

    if not job_candidate:
        print(f"WEBHOOK: No active JobCandidate found for phone {phone} (ignored)")
        return {
            "status": "IGNORED",
            "reason": "No active JobCandidate found",
        }

    if provider_message_id:
        duplicate = db.scalar(
            select(CandidateContact.id)
            .where(CandidateContact.external_message_id == provider_message_id)
            .limit(1)
        )
        if duplicate:
            return {
                "status": "DUPLICATE",
                "job_candidate_id": str(job_candidate.id),
            }

    inbound = CandidateContact(
        job_candidate_id=job_candidate.id,
        channel="WHATSAPP",
        message_type="INBOUND",
        message=text_message,
        response_text=text_message,
        provider="NMVE",
        external_message_id=provider_message_id,
        status="REPLIED",
        responded_at=datetime.utcnow(),
    )
    db.add(inbound)
    db.commit()

    intent = _classify_whatsapp_response(text_message)
    print(f"WEBHOOK: Intent detected = {intent} for message = '{text_message}'")
    inbound.response_intent = intent
    db.commit()

    target_phone = phone
    if not target_phone and job_candidate:
        cand = db.get(Candidate, job_candidate.candidate_id)
        if cand and cand.phone:
            target_phone = cand.phone

    if intent == "INTERESTED":
        print(f"WEBHOOK: Candidate is INTERESTED, updating status and sending CTA to {target_phone}...")
        job_candidate.recruitment_status = "INTERESTED"
        db.commit()

        sent = _send_whatsapp_cta_message(
            raw_phone=target_phone,
            job_candidate_id=str(job_candidate.id),
        )
        print(f"WEBHOOK: CTA send result = {sent}")

        if sent:
            job_candidate.recruitment_status = "INTERVIEW_LINK_SENT"
            db.add(
                CandidateContact(
                    job_candidate_id=job_candidate.id,
                    channel="WHATSAPP",
                    message_type="OUTBOUND",
                    message="Interview scheduling link sent",
                    provider="NMVE",
                    status="SENT",
                    sent_at=datetime.utcnow(),
                )
            )
            db.commit()

    elif intent == "NOT_INTERESTED":
        job_candidate.recruitment_status = "NOT_INTERESTED"
        db.commit()

        ack_msg = (
            "Thank you for letting us know! We appreciate your response and "
            "will keep your profile in mind for future opportunities. Best wishes!"
        )
        sent = _send_whatsapp_text_message(
            raw_phone=target_phone,
            text_message=ack_msg,
        )
        db.add(
            CandidateContact(
                job_candidate_id=job_candidate.id,
                channel="WHATSAPP",
                message_type="OUTBOUND",
                message=ack_msg,
                provider="NMVE",
                status="SENT" if sent else "FAILED",
                sent_at=datetime.utcnow() if sent else None,
            )
        )
        db.commit()

    else:
        clarification = (
            "Thank you for your response. Please reply YES if you are interested "
            "in proceeding with the opportunity, or NO if you are not interested."
        )
        sent = _send_whatsapp_text_message(
            raw_phone=target_phone,
            text_message=clarification,
        )
        db.add(
            CandidateContact(
                job_candidate_id=job_candidate.id,
                channel="WHATSAPP",
                message_type="OUTBOUND",
                message=clarification,
                provider="NMVE",
                status="SENT" if sent else "FAILED",
                sent_at=datetime.utcnow() if sent else None,
            )
        )
        db.commit()

    candidate = db.get(Candidate, job_candidate.candidate_id)
    return {
        "status": intent,
        "job_candidate_id": str(job_candidate.id),
        "candidate_id": str(job_candidate.candidate_id),
        "candidate_name": candidate.name if candidate else "Unknown",
        "message": text_message,
    }


def schedule_candidate_interview(
    db: Session,
    job_candidate_id: UUID,
    scheduled_at: datetime,
    interview_link: str | None = None,
    is_reschedule: bool = False,
) -> dict:
    """Persist the selected interview slot and send the confirmation by WhatsApp."""
    job_candidate = db.get(JobCandidate, job_candidate_id)
    if not job_candidate:
        raise ValueError("JobCandidate not found")

    if job_candidate.recruitment_status == "NOT_INTERESTED":
        raise ValueError("Candidate is not interested")

    import uuid
    from .config import settings
    
    if not is_reschedule:
        if not job_candidate.reschedule_token:
            job_candidate.reschedule_token = str(uuid.uuid4())
    else:
        # Candidate can only reschedule once. Invalidate token so it cannot be used again
        job_candidate.reschedule_token = None
        
    job_candidate.interview_scheduled_at = scheduled_at
    if interview_link:
        if "teams.microsoft.com" not in interview_link:
            job_candidate.interview_link = interview_link
        else:
            job_candidate.interview_link = "https://interview.teckvalley.com/"
    elif not job_candidate.interview_link or "teams.microsoft.com" in (job_candidate.interview_link or ""):
        job_candidate.interview_link = "https://interview.teckvalley.com/"
    job_candidate.recruitment_status = "INTERVIEW_SCHEDULED"
    job_candidate.reminder_24h_sent = False
    job_candidate.reminder_1h_sent = False
    db.commit()

    candidate = db.get(Candidate, job_candidate.candidate_id)

    date_text = scheduled_at.strftime("%d %b %Y, %I:%M %p")
    frontend_url = getattr(settings, 'FRONTEND_URL', 'https://nm-hire-xv-3-c4m5.vercel.app').rstrip('/')
    if not frontend_url or "localhost" in frontend_url or "127.0.0.1" in frontend_url:
        frontend_url = "https://nm-hire-xv-3-c4m5.vercel.app"
    
    if is_reschedule:
        message = (
            "Your interview has been rescheduled successfully! 🎉\n\n"
            f"📅 New Date & Time: {date_text}\n"
        )
        if job_candidate.interview_link:
            message += f"\n🔗 Interview Link:\n{job_candidate.interview_link}\n"
        message += "\nPlease be available a few minutes before the scheduled time."
    else:
        reschedule_link = f"{frontend_url}/reschedule/{job_candidate.reschedule_token}"
        message = (
            "Your interview has been scheduled successfully! 🎉\n\n"
            f"📅 Date & Time: {date_text}\n"
        )
        if job_candidate.interview_link:
            message += f"\n🔗 Interview Link:\n{job_candidate.interview_link}\n"
        message += f"\n🔄 Need to pick a new time? Reschedule here:\n{reschedule_link}\n"
        message += "\nPlease be available a few minutes before the scheduled time."

    sent = _send_whatsapp_text_message(
        raw_phone=candidate.phone if candidate else "",
        text_message=message,
    )

    db.add(
        CandidateContact(
            job_candidate_id=job_candidate.id,
            channel="WHATSAPP",
            message_type="OUTBOUND",
            message=message,
            provider="NMVE",
            status="SENT" if sent else "FAILED",
            sent_at=datetime.utcnow() if sent else None,
        )
    )
    db.commit()

    return {
        "job_candidate_id": str(job_candidate.id),
        "candidate_id": str(job_candidate.candidate_id),
        "scheduled_at": scheduled_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "interview_link": interview_link,
        "status": job_candidate.recruitment_status,
        "confirmation_sent": sent,
    }


def get_outreach_candidates(
    db: Session,
    user_id: UUID,
    candidate_id: UUID | None = None,
) -> list[dict]:
    """Return candidates currently in the WhatsApp recruitment pipeline."""
    q = (
        select(JobCandidate, Job, Candidate)
        .join(Job, Job.id == JobCandidate.job_id)
        .join(Candidate, Candidate.id == JobCandidate.candidate_id)
    )
    if candidate_id:
        q = q.where((Candidate.id == candidate_id) | (JobCandidate.id == candidate_id))
    else:
        q = q.where(
            JobCandidate.recruitment_status.in_([
                "CONTACTED",
                "INTERESTED",
                "NOT_INTERESTED",
                "INTERVIEW_LINK_SENT",
                "INTERVIEW_SCHEDULED",
            ])
        )

    rows = db.execute(q.order_by(JobCandidate.updated_at.desc())).all()

    results = []

    for jc, job, candidate in rows:
        latest_response = db.execute(
            select(CandidateContact)
            .where(
                CandidateContact.job_candidate_id == jc.id,
                CandidateContact.channel == "WHATSAPP",
                CandidateContact.message_type == "INBOUND",
            )
            .order_by(
                CandidateContact.created_at.desc()
            )
        ).scalars().first()

        response_text = (
            latest_response.response_text
            if latest_response
            else None
        )

        response_intent = (
            _classify_whatsapp_response(response_text)
            if response_text
            else None
        )

        responded_at = (
            latest_response.responded_at
            if latest_response
            else None
        )

        latest_outbound = db.scalar(
            select(CandidateContact)
            .where(
                CandidateContact.job_candidate_id == jc.id,
                CandidateContact.channel == "WHATSAPP",
                CandidateContact.message_type == "OUTBOUND",
            )
            .order_by(CandidateContact.created_at.desc())
            .limit(1)
        )
        c_status = (latest_outbound.status if latest_outbound else ("DELIVERED" if response_text or jc.recruitment_status in {"INTERESTED", "INTERVIEW_LINK_SENT", "INTERVIEW_SCHEDULED"} else "DELIVERED")).upper()
        if c_status == "FAILED":
            delivery_status = "FAILED"
        elif c_status in {"INVALID_PHONE", "SKIPPED", "SKIPPED_INVALID_PHONE"}:
            delivery_status = "INVALID_PHONE"
        else:
            delivery_status = "DELIVERED"

        # Exclude failed outreach invitations from default outreach list,
        # but allow viewing if specifically requested by candidate_id
        if delivery_status == "FAILED" and not candidate_id:
            continue

        results.append({
            "id": str(candidate.id),
            "job_id": str(job.id),
            "job_candidate_id": str(jc.id),
            "name": candidate.name or "Unnamed Candidate",
            "phone": candidate.phone or "",
            "job": job.title or "Unknown Role",
            "status": "FAILED" if delivery_status == "FAILED" else jc.recruitment_status,
            "delivery_status": delivery_status,
            "error_message": latest_outbound.message if (latest_outbound and c_status == "FAILED") else None,
            "interview_scheduled_at": (
                jc.interview_scheduled_at.strftime("%Y-%m-%dT%H:%M:%S")
                if jc.interview_scheduled_at
                else None
            ),
            "interview_link": jc.interview_link,
            "score": (
                float(jc.overall_score)
                if jc.overall_score is not None
                else None
            ),
            "rank": jc.ranking_position,
            "response_text": response_text,
            "response_intent": response_intent,
            "responded_at": (
                responded_at.isoformat()
                if responded_at
                else None
            ),
        })

    return results


def update_candidate_status(
    db: Session,
    job_id: UUID,
    candidate_id: UUID,
    status: str,
    target_phone: str | None = None,
):
    """Update recruitment status and trigger initial WhatsApp when appropriate."""
    job_candidate = db.scalar(
        select(JobCandidate).where(
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id == candidate_id,
        )
    )

    if not job_candidate:
        raise ValueError("JobCandidate not found")

    old_status = job_candidate.recruitment_status
    job_candidate.recruitment_status = status.upper()
    db.commit()

    if status.upper() == "CONTACTED" and old_status != "CONTACTED":
        _send_whatsapp_to_candidate(
            db,
            job_id,
            candidate_id,
            target_phone,
        )

    return {
        "job_candidate_id": str(job_candidate.id),
        "candidate_id": str(candidate_id),
        "old_status": old_status,
        "status": job_candidate.recruitment_status,
    }


def bulk_update_candidate_status(
    db: Session,
    job_id: UUID,
    candidate_ids: list[UUID],
    status: str = "CONTACTED",
    target_phone: str | None = None,
) -> dict:
    """Update recruitment status for multiple candidates and trigger WhatsApp invites."""
    results = []
    sent_count = 0
    failed_count = 0

    for c_id in candidate_ids:
        try:
            res = update_candidate_status(
                db=db,
                job_id=job_id,
                candidate_id=c_id,
                status=status,
                target_phone=target_phone,
            )
            results.append({
                "candidate_id": str(c_id),
                "status": "SUCCESS",
                "detail": res,
            })
            sent_count += 1
        except Exception as exc:
            results.append({
                "candidate_id": str(c_id),
                "status": "FAILED",
                "error": str(exc),
            })
            failed_count += 1

    return {
        "job_id": str(job_id),
        "total": len(candidate_ids),
        "sent": sent_count,
        "failed": failed_count,
        "results": results,
    }


def get_all_candidates(db: Session, user_id: UUID) -> list[dict]:
    """Return unique candidates currently in the recruitment workflow."""
    rows = db.execute(
        select(Candidate, JobCandidate, Job)
        .join(
            JobCandidate,
            JobCandidate.candidate_id == Candidate.id,
        )
        .join(
            Job,
            Job.id == JobCandidate.job_id,
        )
        .where(
            JobCandidate.recruitment_status.in_([
                "INTERESTED",
                "INTERVIEW_LINK_SENT",
                "INTERVIEW",
                "INTERVIEW_SCHEDULED",
                "INTERVIEW_COMPLETED",
            ])
        )
        .order_by(
            Candidate.created_at.desc(),
            JobCandidate.created_at.desc(),
        )
    ).all()

    seen = set()
    results = []

    for candidate, jc, job in rows:
        if candidate.id in seen:
            continue
        seen.add(candidate.id)

        score = (
            float(jc.overall_score)
            if jc.overall_score is not None
            else 0
        )

        classification = (
            jc.classification
            or "External Match"
        )

        outbound_interview = (
            db.query(CandidateContact)
            .filter(
                CandidateContact.job_candidate_id == jc.id,
                CandidateContact.channel == "WHATSAPP",
                CandidateContact.message_type == "OUTBOUND",
                CandidateContact.message.contains(
                    "http"
                ),
            )
            .order_by(
                CandidateContact.created_at.desc()
            )
            .first()
        )

        interview_link = None
        if outbound_interview and outbound_interview.message:
            urls = re.findall(
                r"https?://\S+",
                outbound_interview.message,
            )
            if urls:
                interview_link = urls[0].rstrip(
                    "!.,)"
                )

        results.append({
            "id": str(candidate.id),
            "job_id": str(job.id),
            "job_candidate_id": str(jc.id),
            "name": candidate.name or "Unnamed",
            "email": candidate.email,
            "phone": candidate.phone,
            "location": candidate.location or "-",
            "exp": (
                f"{candidate.total_experience_years} yrs"
                if candidate.total_experience_years
                else "-"
            ),
            "score": score,
            "scoreLabel": classification,
            "job": job.title,
            "skills": (
                ", ".join(
                    [
                        (
                            item.get("name")
                            or item.get("skill")
                            or item.get("skill_name")
                            or str(item)
                        )
                        if isinstance(item, dict)
                        else str(item)
                        for item in (
                            candidate.normalized_profile.get(
                                "skills", []
                            )
                            if candidate.normalized_profile
                            else []
                        )[:5]
                    ]
                )
                or "-"
            ),
            "stage": jc.recruitment_status,
            "interview_link": jc.interview_link or interview_link,
            "interview_scheduled_at": (
                jc.interview_scheduled_at.strftime("%Y-%m-%dT%H:%M:%S")
                if jc.interview_scheduled_at
                else None
            ),
            "experience_details": (
                candidate.normalized_profile.get(
                    "experiences", []
                )
                if candidate.normalized_profile
                else []
            ),
            "all_skills": (
                candidate.normalized_profile.get(
                    "skills", []
                )
                if candidate.normalized_profile
                else []
            ),
        })

    return results


# def get_outreach_campaigns(
#     db: Session,
#     user_id: UUID,
# ) -> dict:
#     """Return campaign metrics based on external ranking, not local rescoring."""
#     jobs = db.execute(
#         select(Job)
#         .where(Job.created_by == user_id)
#         .order_by(Job.created_at.desc())
#     ).scalars().all()

#     campaigns = []
#     total_contacted = 0
#     total_pending = 0
#     total_interested = 0

#     for job in jobs:
#         rows = db.execute(
#             select(JobCandidate)
#             .where(JobCandidate.job_id == job.id)
#         ).scalars().all()

#         eligible = sum(
#             1
#             for jc in rows
#             if jc.is_shortlisted
#         )

#         contacted = sum(
#             1
#             for jc in rows
#             if jc.is_shortlisted
#             and jc.recruitment_status in {
#                 "CONTACTED",
#                 "INTERESTED",
#                 "INTERVIEW_LINK_SENT",
#                 "INTERVIEW",
#                 "INTERVIEW_SCHEDULED",
#                 "INTERVIEW_COMPLETED",
#             }
#         )

#         interested = sum(
#             1
#             for jc in rows
#             if jc.recruitment_status in {
#                 "INTERESTED",
#                 "INTERVIEW_LINK_SENT",
#                 "INTERVIEW",
#                 "INTERVIEW_SCHEDULED",
#                 "INTERVIEW_COMPLETED",
#             }
#         )

#         pending = max(eligible - contacted, 0)

#         if contacted == 0:
#             status = "Draft"
#         elif contacted >= eligible and eligible > 0:
#             status = "Completed"
#         else:
#             status = "Active"

#         campaigns.append({
#             "id": str(job.id),
#             "name": job.title,
#             "job": job.title,
#             "created": (
#                 job.created_at.strftime("%b %d, %Y")
#                 if job.created_at
#                 else ""
#             ),
#             "rule": f"Top {eligible} ranked candidates",
#             "eligible": eligible,
#             "contacted": contacted,
#             "interested": interested,
#             "status": status,
#             "searchStr": f"{job.title} {status}".lower(),
#         })

#         total_contacted += contacted
#         total_pending += pending
#         total_interested += interested

#     return {
#         "metrics": {
#             "contacted": total_contacted,
#             "pending": total_pending,
#             "interested": total_interested,
#             "tests_assigned": 0,
#         },
#         "campaigns": campaigns,
#     }


# ============================================================
# NAUKRI-STYLE CANDIDATE ARRAY OUTREACH
# Accepts a plain list of {no, name, role, phone} from the
# recruiter, creates Candidate + JobCandidate rows if they
# don't exist, sends the shortlisting WhatsApp template, and
# records every message in candidate_contacts.
# ============================================================

def _is_automate_yes(val) -> bool:
    """Helper to interpret 'automate' flag (defaulting to True/yes)."""
    if val is None:
        return True
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("yes", "y", "true", "1", "auto")


def send_naukri_outreach_array(
    db: Session,
    job_id: UUID | None = None,
    candidates: list[dict] | None = None,
    company_name: str | None = None,
    user_id: UUID | None = None,
    automate: str | bool | None = "yes",
) -> dict:
    """
    Send the candidate_shortlisted_outreach WhatsApp template to an array of
    candidates supplied by the recruiter or an external system.

    Each entry in ``candidates`` can have:
        - no    : serial number OR phone number (if >= 10 digits)
        - name  : candidate full name
        - role  : applied / shortlisted role
        - phone : WhatsApp-compatible phone number (with or without country code)

    The function:
      1. Determines or creates a Job row (if job_id not given, creates one per role).
      2. Finds or creates a Candidate row (matched by phone).
      3. Finds or creates a JobCandidate row.
      4. Sends the WhatsApp template via NMVE.
      5. Logs the outbound message in candidate_contacts.
      6. Returns a summary dict.
    """
    _company = company_name or getattr(settings, "WHATSAPP_COMPANY_NAME", "the company")

    job = db.get(Job, job_id) if job_id else None

    callback_url = getattr(
        settings,
        "WHATSAPP_CALLBACK_URL",
        "https://nmhirex.onrender.com/api/webhooks/whatsapp",
    )
    template_name = getattr(settings, "WHATSAPP_TEMPLATE_NAME", "candidate_shortlisted_outreach")
    template_language = getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en")

    candidate_list = candidates or []
    results = []
    sent_count = 0
    queued_count = 0
    failed_count = 0
    skipped_count = 0

    for idx, item in enumerate(candidate_list):
        name = str(item.get("user_name") or item.get("name") or "").strip()
        email = str(item.get("email") or "").strip()
        company = str(item.get("current_company") or item.get("company") or "").strip()
        role = str(item.get("job_role") or item.get("role") or (job.title if job else "the position")).strip()
        raw_exp = item.get("experience") or item.get("total_experience_years")
        parsed_exp = None
        if raw_exp is not None and str(raw_exp).strip() != "":
            try:
                parsed_exp = Decimal(str(raw_exp).strip())
            except Exception:
                parsed_exp = None
        
        # Phone can be provided as phone, phone_number, mobile, or in the 'no' field
        raw_phone = str(
            item.get("contact_no")
            or item.get("phone")
            or item.get("phone_number")
            or item.get("mobile")
            or ""
        ).strip()
        serial_no = item.get("no", idx + 1)
        if not raw_phone and item.get("no"):
            no_val = str(item.get("no")).strip()
            digits = "".join(filter(str.isdigit, no_val))
            if len(digits) >= 6:
                raw_phone = no_val
                serial_no = idx + 1

        if not name or not raw_phone:
            results.append({
                "no": serial_no,
                "name": name,
                "phone": raw_phone,
                "status": "SKIPPED_MISSING_FIELDS",
            })
            skipped_count += 1
            continue

        # ----------------------------------------------------------------
        # Find or create Job for this candidate if job_id was not provided
        # ----------------------------------------------------------------
        current_job_id = job.id if job else None
        if not current_job_id:
            role_job = db.scalar(select(Job).where(Job.title == role).limit(1))
            if not role_job:
                creator_id = user_id
                if not creator_id:
                    u = db.scalar(select(User).limit(1))
                    if not u:
                        from .auth import hash_password
                        u = User(
                            name="NM-HireX Admin",
                            email="admin@nmhirex.com",
                            password_hash=hash_password("Admin@123456"),
                            role="ADMIN",
                            status="APPROVED",
                            is_active=True,
                        )
                        db.add(u)
                        db.flush()
                    creator_id = u.id

                role_job = Job(
                    title=role,
                    status="ACTIVE",
                    created_by=creator_id,
                )
                db.add(role_job)
                db.flush()
            current_job_id = role_job.id

        clean_phone = _clean_whatsapp_phone(raw_phone)
        if not clean_phone:
            # Persist candidate so they appear in Dashboard with Invalid Phone / Skipped status
            cand_skipped = db.scalar(
                select(Candidate).where(Candidate.phone == raw_phone)
            )
            if cand_skipped is None:
                cand_skipped = Candidate(
                    name=name,
                    phone=raw_phone,
                    current_role=role,
                    email=email if email else None,
                    current_company=company if company else None,
                    total_experience_years=parsed_exp,
                )
                db.add(cand_skipped)
                db.flush()

            jc_skipped = db.scalar(
                select(JobCandidate).where(
                    JobCandidate.job_id == current_job_id,
                    JobCandidate.candidate_id == cand_skipped.id,
                )
            )
            if jc_skipped is None:
                jc_skipped = JobCandidate(
                    job_id=current_job_id,
                    candidate_id=cand_skipped.id,
                    is_shortlisted=True,
                    recruitment_status="SKIPPED",
                )
                db.add(jc_skipped)
                db.flush()
            else:
                jc_skipped.recruitment_status = "SKIPPED"

            skipped_contact = CandidateContact(
                job_candidate_id=jc_skipped.id,
                channel="WHATSAPP",
                message_type="OUTBOUND",
                message="Skipped: Invalid phone number (<10 digits or incomplete)",
                provider="NMVE",
                status="INVALID_PHONE",
                sent_at=datetime.utcnow(),
            )
            db.add(skipped_contact)
            db.commit()

            results.append({
                "no": serial_no,
                "name": name,
                "phone": raw_phone,
                "status": "SKIPPED_INVALID_PHONE",
                "candidate_id": str(cand_skipped.id),
                "job_candidate_id": str(jc_skipped.id),
            })
            skipped_count += 1
            continue


        # ----------------------------------------------------------------
        # Find or create Candidate (matched by cleaned phone number)
        # ----------------------------------------------------------------
        candidate = db.scalar(
            select(Candidate).where(Candidate.phone == clean_phone)
        )
        if candidate is None:
            # Also try original phone format
            candidate = db.scalar(
                select(Candidate).where(Candidate.phone == raw_phone)
            )

        if candidate is None:
            candidate = Candidate(
                name=name,
                phone=clean_phone,
                current_role=role,
                email=email if email else None,
                current_company=company if company else None,
                total_experience_years=parsed_exp,
            )
            db.add(candidate)
            db.flush()
        else:
            if email and not candidate.email:
                candidate.email = email
            if company and not candidate.current_company:
                candidate.current_company = company
            if role and not candidate.current_role:
                candidate.current_role = role
            if parsed_exp is not None and candidate.total_experience_years is None:
                candidate.total_experience_years = parsed_exp
            db.flush()

        # ----------------------------------------------------------------
        # Find or create JobCandidate
        # ----------------------------------------------------------------
        job_candidate = db.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == current_job_id,
                JobCandidate.candidate_id == candidate.id,
            )
        )
        if job_candidate is None:
            job_candidate = JobCandidate(
                job_id=current_job_id,
                candidate_id=candidate.id,
                is_shortlisted=True,
                recruitment_status="NEW",
            )
            db.add(job_candidate)
            db.flush()


        # ----------------------------------------------------------------
        # Skip if already contacted (avoid duplicate sends)
        # ----------------------------------------------------------------
        already_contacted = _candidate_has_contact_history(db, job_candidate.id)
        if already_contacted:
            results.append({
                "no": serial_no,
                "name": name,
                "phone": clean_phone,
                "status": "SKIPPED_ALREADY_CONTACTED",
                "candidate_id": str(candidate.id),
                "job_candidate_id": str(job_candidate.id),
            })
            skipped_count += 1
            continue

        # ----------------------------------------------------------------
        # Check automation setting ('automate': 'yes' | 'no')
        # If 'no': Candidate is stored in DB for manual review & outreach
        # on the Pending Outreach page. Do NOT send WhatsApp message now.
        # ----------------------------------------------------------------
        item_automate = item.get("automate", automate)
        if not _is_automate_yes(item_automate):
            job_candidate.recruitment_status = "PENDING_OUTREACH"
            db.commit()

            results.append({
                "no": serial_no,
                "name": name,
                "phone": clean_phone,
                "status": "QUEUED_MANUAL",
                "candidate_id": str(candidate.id),
                "job_candidate_id": str(job_candidate.id),
            })
            queued_count += 1
            continue

        # ----------------------------------------------------------------
        # Determine actual destination phone (test mode override)
        # ----------------------------------------------------------------
        dest_phone = clean_phone
        if getattr(settings, "WHATSAPP_TEST_MODE", False):
            test_number = getattr(settings, "WHATSAPP_TEST_NUMBER", "")
            dest_phone = _clean_whatsapp_phone(test_number) or ""
            if not dest_phone:
                results.append({
                    "no": serial_no,
                    "name": name,
                    "phone": clean_phone,
                    "status": "FAILED_TEST_MODE_NO_NUMBER",
                })
                failed_count += 1
                continue

        # ----------------------------------------------------------------
        # Build and send the WhatsApp template payload
        # ----------------------------------------------------------------
        reference_id = f"NMHireX-{str(job_candidate.id)}"

        payload = {
            "to": dest_phone,
            "templateName": template_name,
            "bodyParams": [name, role, _company, _company],
            "languageCode": template_language,
            "referenceId": reference_id,
            "callbackUrl": callback_url,
        }

        print(f"[NaukriOutreach] Sending to {dest_phone} for candidate '{name}' ...")
        success, response_body, provider_message_id = _send_whatsapp_payload(payload)

        if not success:
            failed_contact = CandidateContact(
                job_candidate_id=job_candidate.id,
                channel="WHATSAPP",
                message_type="OUTBOUND",
                message=f"Failed to send template {template_name}: {response_body}",
                provider="NMVE",
                status="FAILED",
                sent_at=datetime.utcnow(),
            )
            db.add(failed_contact)
            job_candidate.recruitment_status = "FAILED"
            db.commit()

            results.append({
                "no": serial_no,
                "name": name,
                "phone": clean_phone,
                "status": "FAILED_SEND",
                "candidate_id": str(candidate.id),
                "job_candidate_id": str(job_candidate.id),
            })
            failed_count += 1
            continue

        # ----------------------------------------------------------------
        # Persist the outbound message
        # ----------------------------------------------------------------
        contact = CandidateContact(
            job_candidate_id=job_candidate.id,
            channel="WHATSAPP",
            message_type="OUTBOUND",
            message=f"Shortlisting template sent: {template_name}",
            provider="NMVE",
            external_message_id=provider_message_id,
            status="DELIVERED",
            sent_at=datetime.utcnow(),
            delivered_at=datetime.utcnow(),
        )
        db.add(contact)

        if job_candidate.recruitment_status in {None, "NEW", "SHORTLISTED"}:
            job_candidate.recruitment_status = "CONTACTED"

        db.commit()

        results.append({
            "no": serial_no,
            "name": name,
            "phone": clean_phone,
            "status": "SENT",
            "candidate_id": str(candidate.id),
            "job_candidate_id": str(job_candidate.id),
        })
        sent_count += 1

    return {
        "job_id": str(job_id) if job_id else None,
        "total": len(candidate_list),
        "sent": sent_count,
        "queued": queued_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "results": results,
    }


def get_pending_outreach_candidates(
    db: Session,
    user_id: UUID | None = None,
) -> list[dict]:
    """
    Return candidates queued for manual outreach (recruitment_status='PENDING_OUTREACH')
    who have not received an outbound WhatsApp outreach message yet.
    """
    query = (
        select(Candidate, JobCandidate, Job)
        .join(JobCandidate, JobCandidate.candidate_id == Candidate.id)
        .outerjoin(Job, Job.id == JobCandidate.job_id)
        .where(JobCandidate.recruitment_status == "PENDING_OUTREACH")
        .order_by(JobCandidate.created_at.desc(), Candidate.created_at.desc())
    )

    rows = db.execute(query).all()
    results = []
    seen = set()

    for candidate, jc, job in rows:
        if jc.id in seen:
            continue
        seen.add(jc.id)

        # Confirm no outbound contact has been made
        has_outbound = _candidate_has_contact_history(db, jc.id)
        if has_outbound:
            continue

        results.append({
            "job_candidate_id": str(jc.id),
            "candidate_id": str(candidate.id),
            "job_id": str(job.id) if job else None,
            "name": candidate.name or "Unnamed Candidate",
            "phone": candidate.phone or "",
            "email": candidate.email or "",
            "company": candidate.current_company or "",
            "role": candidate.current_role or (job.title if job else "Software Engineer"),
            "experience": float(candidate.total_experience_years) if candidate.total_experience_years is not None else None,
            "requisition_id": jc.requisition_id or (str(job.requisition_id) if job and job.requisition_id else None),
            "status": jc.recruitment_status,
            "created_at": jc.created_at.isoformat() if jc.created_at else None,
        })

    return results


def send_pending_outreach_candidates(
    db: Session,
    job_candidate_ids: list[UUID],
) -> dict:
    """
    Send WhatsApp outreach messages (Key 1) to selected pending candidates.
    After sending, sets recruitment_status to 'CONTACTED', logs CandidateContact,
    and returns a summary. The subsequent flow (WhatsApp reply -> slot booking ->
    gateway add_candidate with Key 2 -> confirmation WhatsApp with Key 1) continues
    identically.
    """
    callback_url = getattr(
        settings,
        "WHATSAPP_CALLBACK_URL",
        "https://nmhirex.onrender.com/api/webhooks/whatsapp",
    )
    template_name = getattr(settings, "WHATSAPP_TEMPLATE_NAME", "candidate_shortlisted_outreach")
    template_language = getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", "en")
    default_company = getattr(settings, "WHATSAPP_COMPANY_NAME", "the company")

    results = []
    sent_count = 0
    failed_count = 0
    skipped_count = 0

    for jc_id in job_candidate_ids:
        jc = db.get(JobCandidate, jc_id)
        if not jc:
            results.append({
                "job_candidate_id": str(jc_id),
                "status": "NOT_FOUND",
                "error": "Job candidate record not found",
            })
            failed_count += 1
            continue

        candidate = db.get(Candidate, jc.candidate_id)
        if not candidate:
            results.append({
                "job_candidate_id": str(jc_id),
                "status": "NOT_FOUND",
                "error": "Candidate record not found",
            })
            failed_count += 1
            continue

        job = db.get(Job, jc.job_id) if jc.job_id else None

        # Check if already contacted
        if _candidate_has_contact_history(db, jc.id):
            results.append({
                "job_candidate_id": str(jc.id),
                "name": candidate.name,
                "phone": candidate.phone,
                "status": "SKIPPED_ALREADY_CONTACTED",
            })
            skipped_count += 1
            continue

        clean_phone = _clean_whatsapp_phone(candidate.phone)
        if not clean_phone:
            results.append({
                "job_candidate_id": str(jc.id),
                "name": candidate.name,
                "phone": candidate.phone,
                "status": "INVALID_PHONE",
            })
            failed_count += 1
            continue

        # Test mode override
        dest_phone = clean_phone
        if getattr(settings, "WHATSAPP_TEST_MODE", False):
            test_number = getattr(settings, "WHATSAPP_TEST_NUMBER", "")
            dest_phone = _clean_whatsapp_phone(test_number) or ""
            if not dest_phone:
                results.append({
                    "job_candidate_id": str(jc.id),
                    "name": candidate.name,
                    "phone": clean_phone,
                    "status": "FAILED_TEST_MODE_NO_NUMBER",
                })
                failed_count += 1
                continue

        name = candidate.name or "Candidate"
        role = candidate.current_role or (job.title if job else "the position")
        company = candidate.current_company or default_company

        reference_id = f"NMHireX-{str(jc.id)}"
        payload = {
            "to": dest_phone,
            "templateName": template_name,
            "bodyParams": [name, role, company, company],
            "languageCode": template_language,
            "referenceId": reference_id,
            "callbackUrl": callback_url,
        }

        print(f"[PendingOutreach] Sending WhatsApp to {dest_phone} for candidate '{name}' ...")
        success, response_body, provider_message_id = _send_whatsapp_payload(payload)

        if not success:
            failed_contact = CandidateContact(
                job_candidate_id=jc.id,
                channel="WHATSAPP",
                message_type="OUTBOUND",
                message=f"Failed to send template {template_name}: {response_body}",
                provider="NMVE",
                status="FAILED",
                sent_at=datetime.utcnow(),
            )
            db.add(failed_contact)
            jc.recruitment_status = "FAILED"
            db.commit()

            results.append({
                "job_candidate_id": str(jc.id),
                "name": name,
                "phone": clean_phone,
                "status": "FAILED_SEND",
                "error": str(response_body),
            })
            failed_count += 1
            continue

        # Success: persist outbound contact
        contact = CandidateContact(
            job_candidate_id=jc.id,
            channel="WHATSAPP",
            message_type="OUTBOUND",
            message=f"Shortlisting template sent: {template_name}",
            provider="NMVE",
            external_message_id=provider_message_id,
            status="DELIVERED",
            sent_at=datetime.utcnow(),
            delivered_at=datetime.utcnow(),
        )
        db.add(contact)
        jc.recruitment_status = "CONTACTED"
        db.commit()

        results.append({
            "job_candidate_id": str(jc.id),
            "name": name,
            "phone": clean_phone,
            "status": "SENT",
        })
        sent_count += 1

    return {
        "total": len(job_candidate_ids),
        "sent": sent_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "results": results,
    }
