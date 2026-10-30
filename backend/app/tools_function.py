"""All actual NM-HireX business functions.

Each function is intentionally small and directly composable; LangGraph is not
required for this deterministic pipeline.
"""
from gdown import parse_url
import os
import shutil
import tempfile

import zipfile

import hashlib, json, re, time, logging, os, base64
from pathlib import Path
import gdown
from uuid import UUID
from sqlalchemy import select, delete, text, and_, or_, func, String
from sqlalchemy.orm import Session
from openai import OpenAI
from pypdf import PdfReader
from docx import Document
import pymupdf
from PIL import Image
from .config import settings
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request
from .models import (
    User,
    Job,
    Candidate,
    Resume,
    JobCandidate,
    CandidateContact,
    CandidateSource,
)

OPENAI_API_KEY = settings.OPENAI_API_KEY

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
luna_client = openai_client

OCR_MODEL = "gpt-4o"



import random

WHATSAPP_STAGE_NUMBERS = [
    "919883236730",
    "919064148052",
    "917439717970",
    "919330609485",
]


# ------------------------------------------------------------
# EXTERNAL RESUME MATCHING API
# ------------------------------------------------------------
# The API key is intentionally read from the server environment/settings only.
# Do NOT expose it to the React/frontend application.
RESUME_MATCHING_BASE_URL = os.getenv(
    "RESUME_MATCHING_BASE_URL",
    getattr(
        settings,
        "RESUME_MATCHING_BASE_URL",
        "https://d4u8k6edt3njs.cloudfront.net/api/public/resume-matching/v1",
    ),
).rstrip("/")

RESUME_MATCHING_API_KEY = os.getenv(
    "RESUME_MATCHING_API_KEY",
    getattr(settings, "RESUME_MATCHING_API_KEY", ""),
)


def _resume_matching_request(
    method: str,
    path: str,
    params: dict | None = None,
    body: dict | None = None,
) -> dict | list:
    """Call the external Résumé Matching API using the server-side x-api-key."""
    if not RESUME_MATCHING_API_KEY:
        raise RuntimeError(
            "RESUME_MATCHING_API_KEY is not configured on the server."
        )

    url = f"{RESUME_MATCHING_BASE_URL}/{path.lstrip('/')}"

    if params:
        clean_params = {
            key: value
            for key, value in params.items()
            if value is not None and value != ""
        }
        if clean_params:
            url = f"{url}?{urllib.parse.urlencode(clean_params)}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "NM-HireX/1.0",
        "x-api-key": RESUME_MATCHING_API_KEY,
    }

    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method.upper(),
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw_response": raw}

    except urllib.error.HTTPError as error:
        try:
            error_body = error.read().decode("utf-8", errors="replace")
        except Exception:
            error_body = str(error)
        raise RuntimeError(
            f"Résumé Matching API returned HTTP {error.code}: {error_body}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Could not connect to Résumé Matching API: {error}"
        ) from error


def get_resume_matching_requisitions(
    status: str | None = "open",
    department: str | None = None,
    q: str | None = None,
    period: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    sort: str | None = "status",
    limit: int = 50,
    offset: int = 0,
    include: str | None = None,
    end_user: str | None = None,
) -> dict | list:
    """
    API 1: list requisitions from the external Résumé Matching API.

    The external contract uses `q` (not `search`) and uses India-calendar
    periods/dates. `include=details` is supported for the requisition picker
    and does not start a Sheela reading.
    """
    if include == "details":
        limit = min(limit, 20)
    else:
        limit = min(limit, 200)

    limit = max(1, int(limit))
    offset = max(0, int(offset))

    return _resume_matching_request(
        "GET",
        "/requisitions",
        params={
            "status": status,
            "department": department,
            "q": q,
            "period": period,
            "created_from": created_from,
            "created_to": created_to,
            "sort": sort,
            "limit": limit,
            "offset": offset,
            "include": include,
            "end_user": end_user,
        },
    )


def _extract_requisition_items(payload) -> list[dict]:
    """Normalize the external /requisitions response into requisition dictionaries."""
    if payload is None:
        return []

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("requisitions", "results", "items", "data", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_requisition_items(value)
            if nested:
                return nested

    if any(
        key in payload
        for key in (
            "vereq_number",
            "vereQ",
            "vereq",
            "requisition_number",
            "req_number",
        )
    ):
        return [payload]

    return []


def _requisition_value(item: dict, *keys):
    """Return the first non-empty requisition field."""
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return None


def create_job_from_resume_matching_requisition(
    db: Session,
    user_id: UUID,
    vereq_number: str,
    end_user: str | None = None,
) -> Job:
    """
    Create a local NM-HireX Job from API 1's requisition details.

    No local JD extraction or candidate scoring is run. The external API is
    the source of the requisition/JD content for this flow.
    """
    vereq_number = str(vereq_number).strip()
    if not vereq_number:
        raise ValueError("VEREQ number is required")

    # Check if a Job for this vereq_number already exists for this user
    existing_sources = db.scalars(
        select(JobSource)
        .join(Job, Job.id == JobSource.job_id)
        .where(
            Job.created_by == user_id,
            JobSource.source_name == "RESUME_MATCHING"
        )
    ).all()
    
    for source in existing_sources:
        if source.search_criteria and source.search_criteria.get("vereq_number") == vereq_number:
            return db.get(Job, source.job_id)

    payload = get_resume_matching_requisitions(
        status="all",
        q=vereq_number,
        include="details",
        limit=20,
        offset=0,
        end_user=end_user,
    )
    requisitions = _extract_requisition_items(payload)

    selected = None
    target = vereq_number.lower()

    for item in requisitions:
        value = _requisition_value(
            item,
            "label",
            "vereq_number",
            "vereQ",
            "vereq",
            "requisition_number",
            "req_number",
            "number",
            "id",
        )
        if value is not None and str(value).strip().lower() == target:
            selected = item
            break

        # The API accepts the numeric form too: 1187 == VEREQ1187.
        normalized_value = str(value).strip().lower() if value is not None else ""
        normalized_target = target.removeprefix("vereq")
        normalized_value = normalized_value.removeprefix("vereq")
        if normalized_value and normalized_value == normalized_target:
            selected = item
            break

    if selected is None and len(requisitions) == 1:
        selected = requisitions[0]

    if selected is None:
        raise ValueError(
            f"VEREQ {vereq_number} was not found in Resume Matching API requisitions."
        )

    title = _requisition_value(
        selected,
        "title",
        "job_title",
        "requisition_title",
        "role",
        "name",
    ) or f"Requisition {vereq_number}"

    description = _requisition_value(
        selected,
        "description",
        "job_description",
        "jobDescription",
    )
    requirements = _requisition_value(
        selected,
        "requirements",
    )
    responsibilities = _requisition_value(
        selected,
        "responsibilities",
    )

    description_parts = [
        str(value).strip()
        for value in (description, requirements, responsibilities)
        if value
    ]
    combined_description = "\n\n".join(description_parts) or None

    location = _requisition_value(
        selected,
        "location",
        "job_location",
        "city",
    )
    work_mode = _requisition_value(
        selected,
        "work_mode",
        "workMode",
        "mode",
    )

    job = Job(
        created_by=user_id,
        title=str(title)[:255],
        description=combined_description,
        location=str(location)[:255] if location else None,
        work_mode=str(work_mode)[:50] if work_mode else None,
        status="READY",
    )

    db.add(job)
    db.flush()

    # Save the external requisition details so NM-HireX retains the JD source
    # and can reproduce the same external matching flow later.
    job_source = JobSource(
        job_id=job.id,
        source_name="RESUME_MATCHING",
        search_criteria={
            "vereq_number": vereq_number,
            "sort": "sheela",
            "include": "details",
            "requisition": selected,
        },
        status="READY",
        candidates_found=0,
        searched_at=datetime.utcnow(),
    )
    db.add(job_source)

    # Populate the existing structured JD table without asking another model
    # to extract the requisition. The external API already provides the key
    # skills and Sheela checklist.
    checks = selected.get("what_sheela_checks")
    mandatory = []
    preferred = []
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            label = check.get("label") or check.get("short")
            if not label:
                continue
            if check.get("must") is True:
                mandatory.append(str(label))
            else:
                preferred.append(str(label))

    key_skills = selected.get("key_skills")
    if isinstance(key_skills, list):
        for skill in key_skills:
            skill_text = str(skill).strip()
            if skill_text and skill_text not in mandatory and skill_text not in preferred:
                mandatory.append(skill_text)

    try:
        existing_req = db.scalar(
            select(JobRequirement).where(JobRequirement.job_id == job.id)
        )
        if existing_req is None:
            existing_req = JobRequirement(
                job_id=job.id,
                job_title=str(title)[:255],
                minimum_experience=safe_float(
                    selected.get("min_experience_years")
                ),
                location=str(location)[:255] if location else None,
                work_mode=str(work_mode)[:50] if work_mode else None,
                mandatory_skills=mandatory,
                preferred_skills=preferred,
                responsibilities=[responsibilities] if responsibilities else [],
                other_requirements=[requirements] if requirements else [],
                extraction_model="external-resume-matching-v1",
                extraction_version="external-requisition-details",
            )
            db.add(existing_req)
    except Exception:
        logging.exception("Failed to populate JobRequirement from external requisition")

    db.commit()
    db.refresh(job)
    return job


def get_resume_matching_matches(
    vereq_number: str,
    sort: str | None = None,
    top: int = 100,
    detail: str = "full",
    limit: int = 100,
    offset: int = 0,
    list_id: str | None = None,
    source: str = "any",
    hide_in_requisition: bool = False,
    hide_below_minimum: bool = False,
    min_match_pct: int = 0,
    sheela_min_verdict: str | None = None,
    min_sheela_score: int = 0,
    exclude_person_ids: str | None = None,
    q: str | None = None,
    sheela: str = "auto",
    end_user: str | None = None,
) -> dict | list:
    """
    API 2: get matched candidates for one VEREQ.

    `sort=sheela` returns Sheela's order. `sheela=auto` starts/joins the
    reading when the key permits it.
    """
    if not vereq_number or not str(vereq_number).strip():
        raise ValueError("VEREQ number is required")

    top = int(top)
    if top not in {50, 100, 200, 500, 1000}:
        raise ValueError("top must be one of 50, 100, 200, 500, 1000")

    detail = str(detail or "full").lower()
    if detail not in {"full", "summary"}:
        raise ValueError("detail must be full or summary")

    max_limit = 100 if detail == "full" else 200
    limit = max(1, min(int(limit), max_limit))

    encoded_vereq = urllib.parse.quote(str(vereq_number).strip(), safe="")

    return _resume_matching_request(
        "GET",
        f"/requisitions/{encoded_vereq}/matches",
        params={
            "top": top,
            "detail": detail,
            "limit": limit,
            "offset": max(0, int(offset)),
            "list_id": list_id,
            "sort": sort,
            "source": source,
            "hide_in_requisition": str(hide_in_requisition).lower(),
            "hide_below_minimum": str(hide_below_minimum).lower(),
            "min_match_pct": min_match_pct,
            "sheela_min_verdict": sheela_min_verdict,
            "min_sheela_score": min_sheela_score,
            "exclude_person_ids": exclude_person_ids,
            "q": q,
            "sheela": sheela,
            "end_user": end_user,
        },
    )


def _extract_poll_seconds(payload) -> int | None:
    """Find poll_after_seconds in the common response shapes."""
    if not isinstance(payload, dict):
        return None

    for key in ("poll_after_seconds", "pollAfterSeconds"):
        value = payload.get(key)
        if value is not None:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                pass

    for key in ("data", "result", "meta"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            seconds = _extract_poll_seconds(nested)
            if seconds is not None:
                return seconds

    return None


def _extract_match_items(payload) -> list[dict]:
    """
    Normalize the external API response into a list of candidate dictionaries.

    The API documentation supplied to NM-HireX describes ranked matches but does
    not provide a fixed response example here, so this helper accepts the common
    `matches`, `candidates`, `results`, `items`, `data`, and `result` shapes.
    """
    if payload is None:
        return []

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("matches", "candidates", "results", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    for key in ("data", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_match_items(value)
            if nested:
                return nested

    # A single candidate object can also be returned directly.
    candidate_keys = {
        "name", "full_name", "candidate_name", "email", "phone",
        "resume_url", "resume_link", "resume", "person_id",
        "candidate_id",
        "external_candidate_id", "score", "rank", "ranking",
    }
    if candidate_keys.intersection(payload.keys()):
        return [payload]

    return []


def _candidate_value(item: dict, *keys):
    """Return the first non-empty value from a candidate payload."""
    for key in keys:
        value = item.get(key)
        if value is not None and value != "":
            return value
    return None


def _resume_text_from_match(item: dict) -> str | None:
    """Extract full résumé text/reading when the external API returns it."""
    value = _candidate_value(
        item,
        "resume_text",
        "full_resume",
        "full_resume_text",
        "resume_reading",
        "full_reading",
        "resume_content",
        "text",
    )
    if isinstance(value, str) and value.strip():
        return value.strip()

    resume = item.get("resume")
    if isinstance(resume, dict):
        value = _candidate_value(
            resume,
            "text",
            "full_text",
            "content",
            "reading",
        )
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _resume_url_from_match(item: dict) -> str | None:
    """Extract the résumé download/profile URL from the external payload."""
    value = _candidate_value(
        item,
        "resume_url",
        "resume_link",
        "resume_download_url",
        "download_url",
        "profile_url",
    )
    if isinstance(value, str):
        return value.strip() or None

    resume = item.get("resume")
    if isinstance(resume, dict):
        value = _candidate_value(
            resume,
            "url",
            "download_url",
            "link",
        )
        if isinstance(value, str):
            return value.strip() or None

    return None


def _external_candidate_id(item: dict, resume_url: str | None) -> str:
    """Create a stable source ID when the API does not return one explicitly."""
    value = _candidate_value(
        item,
        "candidate_id",
        "external_candidate_id",
        "id",
        "profile_id",
        "candidateId",
    )
    if value is not None:
        return str(value)

    email = _candidate_value(item, "email", "email_address")
    if email:
        return str(email).strip().lower()

    phone = _candidate_value(item, "phone", "mobile", "phone_number")
    name = _candidate_value(item, "name", "full_name", "candidate_name")
    stable = f"{name or ''}|{phone or ''}|{resume_url or ''}"
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def poll_resume_matching_matches(
    vereq_number: str,
    max_attempts: int | None = None,
    default_wait_seconds: int | None = None,
    top: int = 100,
    end_user: str | None = None,
) -> dict | list:
    """
    Call API 2, wait according to meta.sheela.poll_after_seconds, then call
    again in Sheela order until the reading is complete or the safety limit is
    reached.
    """
    max_attempts = max_attempts or int(
        getattr(settings, "RESUME_MATCHING_POLL_MAX_ATTEMPTS", 6) or 6
    )
    default_wait_seconds = default_wait_seconds or int(
        getattr(settings, "RESUME_MATCHING_POLL_DEFAULT_WAIT_SECONDS", 5) or 5
    )

    first = get_resume_matching_matches(
        vereq_number,
        top=top,
        detail="full",
        limit=min(top, 100),
        sort=None,
        sheela="auto",
        end_user=end_user,
    )

    current = first
    for attempt in range(max_attempts + 1):
        poll_after = _extract_poll_seconds(current)

        if poll_after is None:
            # No active reading remains. Ensure the stored order is Sheela order.
            if attempt == 0 or not _extract_match_items(current):
                return get_resume_matching_matches(
                    vereq_number,
                    sort="sheela",
                    top=top,
                    detail="full",
                    limit=min(top, 100),
                    sheela="auto",
                    end_user=end_user,
                )
            return current

        if attempt >= max_attempts:
            logging.warning(
                "Sheela polling limit reached for VEREQ %s; returning latest response.",
                vereq_number,
            )
            return current

        wait_seconds = max(0, int(poll_after or default_wait_seconds))
        if wait_seconds:
            time.sleep(wait_seconds)

        current = get_resume_matching_matches(
            vereq_number,
            sort="sheela",
            top=top,
            detail="full",
            limit=min(top, 100),
            sheela="auto",
            end_user=end_user,
        )

    return current


def _create_candidate_from_external_match(
    db: Session,
    item: dict,
    source_name: str = "RESUME_MATCHING",
) -> tuple[Candidate, CandidateSource, bool]:
    """Create or update one local Candidate from an external match."""
    resume_url = _resume_url_from_match(item)
    external_id = _external_candidate_id(item, resume_url)

    source = db.scalar(
        select(CandidateSource).where(
            CandidateSource.source_name == source_name,
            CandidateSource.external_candidate_id == external_id,
        )
    )

    candidate = None
    created = False

    if source:
        candidate = db.get(Candidate, source.candidate_id)

    if candidate is None:
        email = _candidate_value(item, "email", "email_address")
        if email:
            candidate = db.scalar(
                select(Candidate).where(
                    func.lower(Candidate.email) == str(email).strip().lower()
                )
            )

    name = _candidate_value(item, "name", "full_name", "candidate_name")
    email = _candidate_value(item, "email", "email_address")
    phone = _candidate_value(item, "phone", "mobile", "phone_number")
    location = _candidate_value(item, "location", "city", "current_location")
    current_company = _candidate_value(
        item,
        "current_company",
        "company",
        "currentCompany",
    )
    current_role = _candidate_value(
        item,
        "current_role",
        "role",
        "designation",
        "currentRole",
    )
    experience = _candidate_value(
        item,
        "total_experience_years",
        "experience_years",
        "experience",
    )
    notice_period = _candidate_value(
        item, 
        "notice_period_days",
        "notice_period",
        "noticePeriodDays",
    )
    profile_summary = _candidate_value(
        item,
        "profile_summary",
        "summary",
        "headline",
    )
    resume_text = _resume_text_from_match(item)

    if candidate is None:
        candidate = Candidate(
            name=str(name or external_id)[:255],
            email=str(email)[:255] if email else None,
            phone=str(phone)[:50] if phone else None,
            location=str(location)[:255] if location else None,
            total_experience_years=safe_float(experience),
            current_company=str(current_company)[:255] if current_company else None,
            current_role=str(current_role)[:255] if current_role else None,
            notice_period_days=(
                int(safe_float(notice_period))
                if safe_float(notice_period) is not None
                else None
            ),
            profile_summary=str(profile_summary) if profile_summary else None,
            raw_profile_text=resume_text,
            normalized_profile=item,
        )
        db.add(candidate)
        db.flush()
        created = True
    else:
        # Fill only missing local fields; do not overwrite recruiter/DB data
        # with an incomplete external payload.
        if not candidate.name and name:
            candidate.name = str(name)[:255]
        if not candidate.email and email:
            candidate.email = str(email)[:255]
        if not candidate.phone and phone:
            candidate.phone = str(phone)[:50]
        if not candidate.location and location:
            candidate.location = str(location)[:255]
        if candidate.total_experience_years is None and experience is not None:
            candidate.total_experience_years = safe_float(experience)
        if not candidate.current_company and current_company:
            candidate.current_company = str(current_company)[:255]
        if not candidate.current_role and current_role:
            candidate.current_role = str(current_role)[:255]
        if candidate.notice_period_days is None and notice_period is not None:
            parsed_notice = safe_float(notice_period)
            if parsed_notice is not None:
                candidate.notice_period_days = int(parsed_notice)
        if not candidate.profile_summary and profile_summary:
            candidate.profile_summary = str(profile_summary)
        if resume_text and not candidate.raw_profile_text:
            candidate.raw_profile_text = resume_text
        if not candidate.normalized_profile:
            candidate.normalized_profile = item

    if source is None:
        source = CandidateSource(
            candidate_id=candidate.id,
            source_name=source_name,
            external_candidate_id=external_id,
            profile_url=resume_url,
            raw_source_data=item,
            fetched_at=datetime.utcnow(),
        )
        db.add(source)
    else:
        source.profile_url = resume_url or source.profile_url
        source.raw_source_data = item
        source.fetched_at = datetime.utcnow()
        source.candidate_id = candidate.id

    # Store the external résumé URL/text in the existing Resume table so the
    # current NM-HireX frontend can use the same resume field it already expects.
    if resume_url or resume_text:
        existing_resume = db.scalar(
            select(Resume)
            .where(Resume.candidate_id == candidate.id)
            .order_by(Resume.uploaded_at.desc())
        )

        if existing_resume is None:
            file_name = f"{external_id}.resume"
            if resume_url:
                try:
                    parsed = urllib.parse.urlparse(resume_url)
                    candidate_name = Path(parsed.path).name
                    if candidate_name:
                        file_name = candidate_name[:255]
                except Exception:
                    pass

            db.add(
                Resume(
                    candidate_id=candidate.id,
                    file_name=file_name,
                    file_url=resume_url,
                    file_type=(
                        Path(urllib.parse.urlparse(resume_url).path).suffix
                        .lower()
                        .lstrip(".")
                        if resume_url
                        else None
                    ),
                    file_size=None,
                    file_hash=None,
                    raw_text=resume_text,
                    parsed_data=item,
                    parsing_status="COMPLETED" if resume_text else "PENDING",
                    extraction_status="COMPLETED" if resume_text else "PENDING",
                    extraction_model=(
                        settings.EXTRACTION_MODEL if resume_text else None
                    ),
                    extraction_version="external-resume-matching-v1",
                )
            )
        else:
            if resume_url:
                existing_resume.file_url = resume_url
            if resume_text and not existing_resume.raw_text:
                existing_resume.raw_text = resume_text
                existing_resume.parsed_data = item
                existing_resume.parsing_status = "COMPLETED"

    db.flush()
    return candidate, source, created


def _sheela_data(item: dict) -> dict:
    value = item.get("sheela")
    return value if isinstance(value, dict) else {}


def _external_match_score(item: dict):
    """Return Sheela's 0-100 score. Resume-match score is only a fallback."""
    sheela = _sheela_data(item)
    score = _candidate_value(sheela, "score")
    if score is not None:
        return safe_float(score)

    # Some API states can return a direct score field. Keep it as a fallback.
    direct = _candidate_value(item, "sheela_score", "score")
    if direct is not None:
        return safe_float(direct)

    return None


def _external_rank(item: dict, fallback_rank: int) -> int:
    sheela = _sheela_data(item)
    rank = _candidate_value(sheela, "sheela_rank")
    if rank is not None:
        try:
            return int(rank)
        except (TypeError, ValueError):
            pass

    rank = _candidate_value(item, "rank")
    if rank is not None:
        try:
            return int(rank)
        except (TypeError, ValueError):
            pass

    return fallback_rank


def sync_resume_matching_candidates(
    db: Session,
    job_id: UUID,
    vereq_number: str,
    top_n: int = 100,
    poll: bool = True,
    end_user: str | None = None,
) -> dict:
    """
    Fetch external matches for a VEREQ and attach them to an NM-HireX Job.

    The external Resume Matching API is the source of truth for matching,
    ranking and candidate score. NM-HireX stores that score in
    JobCandidate.overall_score and does not recalculate it here.
    """
    job = db.get(Job, job_id)
    if not job:
        raise ValueError("Job not found")

    vereq_number = str(vereq_number).strip()
    if not vereq_number:
        raise ValueError("VEREQ number is required")

    payload = (
        poll_resume_matching_matches(vereq_number, top=max(100, top_n), end_user=end_user)
        if poll
        else get_resume_matching_matches(
            vereq_number,
            sort="sheela",
            top=max(100, top_n),
            detail="full",
            limit=min(max(100, top_n), 100),
            sheela="auto",
            end_user=end_user,
        )
    )

    matches = _extract_match_items(payload)
    if not matches:
        raise ValueError(
            f"No candidate matches were returned for VEREQ {vereq_number}."
        )

    # Keep the VEREQ in the existing JobSource JSON rather than requiring a new
    # database column/migration just for this integration.
    job_source = db.scalar(
        select(JobSource).where(
            JobSource.job_id == job_id,
            JobSource.source_name == "RESUME_MATCHING",
        ).order_by(JobSource.searched_at.desc())
    )

    if job_source is None:
        job_source = JobSource(
            job_id=job_id,
            source_name="RESUME_MATCHING",
        )
        db.add(job_source)

    job_source.search_criteria = {
        "vereq_number": vereq_number,
        "sort": "sheela",
    }
    job_source.status = "COMPLETED"
    job_source.candidates_found = len(matches)
    job_source.searched_at = datetime.utcnow()

    saved = []
    shortlist_limit = int(getattr(settings, "OUTREACH_TOP_N", 50) or 50)

    for index, item in enumerate(matches[:top_n], start=1):
        try:
            candidate, source, created = _create_candidate_from_external_match(
                db,
                item,
                source_name="RESUME_MATCHING",
            )

            jc = db.scalar(
                select(JobCandidate).where(
                    JobCandidate.job_id == job_id,
                    JobCandidate.candidate_id == candidate.id,
                )
            )

            parsed_score = _external_match_score(item)
            sheela_rank = _external_rank(item, index)

            if jc is None:
                jc = JobCandidate(
                    job_id=job_id,
                    candidate_id=candidate.id,
                    source_id=source.id,
                    eligibility_status="PENDING",
                    recruitment_status="NEW",
                    overall_score=parsed_score,
                    classification="External Match",
                    ranking_position=sheela_rank,
                    is_shortlisted=(sheela_rank <= shortlist_limit),
                )
                db.add(jc)
            else:
                jc.source_id = source.id
                jc.ranking_position = sheela_rank
                jc.overall_score = parsed_score
                jc.classification = "External Match"

                # Preserve the candidate once they have entered the recruitment
                # workflow, even if a later re-sync moves them below rank 50.
                if jc.recruitment_status in {None, ""}:
                    jc.recruitment_status = "NEW"
                jc.is_shortlisted = (
                    jc.is_shortlisted
                    or index <= shortlist_limit
                )

            saved.append({
                "rank": sheela_rank,
                "candidate_id": str(candidate.id),
                "name": candidate.name,
                "email": candidate.email,
                "phone": candidate.phone,
                "resume_url": _resume_url_from_match(item),
                "score": parsed_score,
                "sheela_score": parsed_score,
                "external_candidate_id": source.external_candidate_id,
                "created": created,
                "is_shortlisted": sheela_rank <= shortlist_limit,
            })

        except Exception as error:
            logging.exception(
                "Failed to save external candidate at rank %s for VEREQ %s",
                index,
                vereq_number,
            )
            # Continue saving the remaining candidates.
            continue

    db.commit()

    return {
        "job_id": str(job_id),
        "vereq_number": vereq_number,
        "source": "RESUME_MATCHING",
        "total_matches_returned": len(matches),
        "candidates_saved": len(saved),
        "candidates": saved,
    }


# ------------------------------------------------------------
# FILE HELPERS
# ------------------------------------------------------------
# def _text_is_insufficient(text: str) -> bool:
#     """Return True when native PDF extraction is too sparse to trust."""
#     cleaned = re.sub(r"\s+", " ", text or "").strip()
#     if len(cleaned) < 250:
#         return True

#     # A page containing mostly symbols/noise is also a good OCR candidate.
#     alnum = sum(ch.isalnum() for ch in cleaned)
#     return alnum < max(100, int(len(cleaned) * 0.45))


# def _ocr_pdf_page(page, page_number: int, native_text: str) -> str:
#     """Render one PDF page and use GPT-5.6 Luna to recover only image-based text.

#     Native pypdf text is preserved. Luna is asked for additional text visible
#     in the page image so partial image sections are not lost or duplicated.
#     """
#     if luna_client is None:
#         logging.warning(
#             "OPENAI_API_KEY is not configured; skipping OCR for page %s.",
#             page_number,
#         )
#         return ""

#     try:
#         pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
#         image_bytes = pix.tobytes("png")
#         image_b64 = base64.b64encode(image_bytes).decode("utf-8")

#         response = luna_client.responses.create(
#             model=OCR_MODEL,
#             input=[
#                 {
#                     "role": "user",
#                     "content": [
#                         {
#                             "type": "input_text",
#                             "text": (
#                                 "Recover text from image-based content on this CV page. "
#                                 "The native PDF text extracted by pypdf is provided below. "
#                                 "Return ONLY additional readable text that is present in the "
#                                 "page image but missing from the native text. This includes "
#                                 "image-based experience, skills, education, certifications, "
#                                 "projects, tables, dates, companies, job titles and other "
#                                 "resume information. Do not repeat text already represented "
#                                 "in the native text. Do not summarize. Do not invent or infer. "
#                                 "If the image contains no additional text, return an empty "
#                                 "response.\n\n"
#                                 f"NATIVE PDF TEXT:\n{native_text[:12000]}"
#                             ),
#                         },
#                         {
#                             "type": "input_image",
#                             "image_url": f"data:image/png;base64,{image_b64}",
#                         },
#                     ],
#                 }
#             ],
#         )

#         return (response.output_text or "").strip()

#     except Exception as error:
#         logging.warning(
#             "OCR failed for PDF page %s: %s",
#             page_number,
#             error,
#         )
#         return ""


# def _read_pdf_with_ocr(path: str) -> str:
#     """Extract PDF text with pypdf and OCR only pages where native text is insufficient."""
#     p = Path(path)
#     pypdf_logger = logging.getLogger("pypdf")
#     previous_level = pypdf_logger.level

#     try:
#         pypdf_logger.setLevel(logging.ERROR)

#         reader = PdfReader(str(p))

#         extracted_text = "\n".join(
#             (page.extract_text() or "")
#             for page in reader.pages
#         )

#         if _text_is_insufficient(extracted_text):
#             print(f"   [INFO] PDF {p.name} appears to be scanned. Running OCR fallback...")
#             try:
#                 ocr_text = []
#                 doc = pymupdf.open(str(p))
#                 for page_num, page in enumerate(doc):
#                     native_page_text = ""
#                     if page_num < len(reader.pages):
#                         native_page_text = reader.pages[page_num].extract_text() or ""
#                     page_text = _ocr_pdf_page(page, page_num, native_page_text)
#                     ocr_text.append(page_text)
#                 extracted_text = extracted_text + "\n" + "\n".join(ocr_text)
#             except Exception as e:
#                 print(f"   [WARNING] OCR fallback failed for {p.name}: {e}")

#         return extracted_text

#     finally:
#         pypdf_logger.setLevel(previous_level)


# def read_file(path: str) -> str:
#     """
#     Read a supported PDF, DOCX, or TXT file.

#     PDFs use pypdf first and GPT-5.6 Luna only as a fallback for
#     scanned/image-heavy pages. The returned text is then passed unchanged
#     into the existing JSON extraction pipeline.
#     """
#     p = Path(path)

#     if p.suffix.lower() == ".pdf":
#         return _read_pdf_with_ocr(str(p))  

#     if p.suffix.lower() == ".docx":
#         doc = Document(str(p))
#         text_lines = []
#         for paragraph in doc.paragraphs:
#             if paragraph.text.strip():
#                 text_lines.append(paragraph.text.strip())
#         for table in doc.tables:
#             for row in table.rows:
#                 row_text = []
#                 for cell in row.cells:
#                     if cell.text.strip():
#                         row_text.append(cell.text.strip().replace('\n', ' '))
#                 if row_text:
#                     text_lines.append(" | ".join(row_text))
#         return "\n".join(text_lines)

#     if p.suffix.lower() == ".txt":
#         return p.read_text(
#             encoding="utf-8",
#             errors="ignore"
#         ) 

#     if p.suffix.lower() in [".png", ".jpg", ".jpeg"]:
#         try:
#             if luna_client is None:
#                 raise ValueError("OPENAI_API_KEY is not configured; cannot OCR image files.")
#             img = Image.open(str(p))
#             from io import BytesIO
#             buffered = BytesIO()
#             img.save(buffered, format="PNG")
#             image_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
#             response = luna_client.responses.create(
#                 model=OCR_MODEL,
#                 input=[{
#                     "role": "user",
#                     "content": [
#                         {"type": "input_text", "text": "Extract all text from this resume image exactly as it appears. Do not add any formatting or commentary."},
#                         {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"}
#                     ]
#                 }]
#             )
#             return (response.output_text or "").strip()
#         except Exception as e:
#             raise ValueError(f"Failed to extract text from image: {e}")

#     raise ValueError(
#         f"Unsupported file type: {p.suffix}"
#     )

# def file_hash(path: str) -> str:
#     """Input: file path. Output: SHA-256 hex digest used for duplicate detection."""
#     h = hashlib.sha256()
#     with open(path, "rb") as f:
#         for block in iter(lambda: f.read(1024 * 1024), b""):
#             h.update(block)
#     return h.hexdigest()



# ------------------------------------------------------------
# AI EXTRACTION
# ------------------------------------------------------------
# def _json_completion(prompt: str, model: str) -> dict:
#     """Input: prompt/model. Output: validated JSON object returned by the configured LLM."""
#     response = openai_client.chat.completions.create(
#         model=model,
#         response_format={"type": "json_object"},
#         messages=[{"role": "system", "content": "Return only valid JSON."}, {"role": "user", "content": prompt}],
#     )
#     return json.loads(response.choices[0].message.content)

# def extract_jd(text: str) -> dict:
#     """Input: JD text. Output: structured JD requirements. Unknown facts must be null/empty."""
#     prompt = f"""
# Extract this job description into JSON with exactly these keys:
# job_title, min_experience_years, max_experience_years, mandatory_skills,
# preferred_skills, education, certifications, domains, responsibilities,
# location, work_mode, notice_period_days, other_requirements, confidence_score.
# Rules: preserve specific skills exactly; only classify a skill as mandatory when
# required/essential; words such as advantageous/preferred/nice-to-have belong in
# preferred_skills; never infer missing experience, location, notice period or education.
# JD:\n{text[:30000]}
# """
#     return _json_completion(prompt, settings.EXTRACTION_MODEL)

# def extract_resume(text: str) -> dict:
#     """Input: CV text. Output: structured candidate profile with explicit nulls for unsupported facts."""
#     prompt = f"""
# Extract the CV into JSON with exactly these keys:
# name, email, phone, location, total_experience_years, current_company, current_role,
# notice_period_days, profile_summary, skills, experiences, education, certifications, projects.
# Rules: never guess missing values; never turn a technology into a company or role;
# preserve specific skills such as Django as Django and use parent_skill only as a relationship.
# CV:\n{text[:30000]}
# """
#     return _json_completion(prompt, settings.EXTRACTION_MODEL)

# def normalize_skill(name: str) -> tuple[str, str | None, str | None]:
#     """
#     Normalize a candidate skill while preserving the original specific technology.

#     Input:
#         name -> Skill name.

#     Output:
#         Tuple containing:
#         - normalized skill
#         - parent skill
#         - skill category

#     Example:
#         Django -> Django, Python, Backend
#         DRF -> Django REST Framework, Django, Backend
#     """

#     if name is None:
#         return "", None, None

#     raw = str(name).strip()

#     if not raw:
#         return "", None, None

#     low = raw.lower()

#     relationships = {
#         "django": ("Django", "Python", "Backend"),
#         "django rest framework": (
#             "Django REST Framework",
#             "Django",
#             "Backend"
#         ),
#         "drf": (
#             "Django REST Framework",
#             "Django",
#             "Backend"
#         ),
#         "flask": ("Flask", "Python", "Backend"),
#         "fastapi": ("FastAPI", "Python", "Backend"),
#         "spring boot": ("Spring Boot", "Java", "Backend"),
#         "react.js": ("React", "JavaScript", "Frontend"),
#         "react": ("React", "JavaScript", "Frontend"),
#     }

#     if low in relationships:
#         return relationships[low]

#     return raw, None, None

# def safe_list(value) -> list:
#     """
#     Convert an extracted value into a safe list.

#     Input:
#         value -> GPT extracted value.

#     Output:
#         Always returns a list.

#     Examples:
#         None -> []
#         "Python" -> ["Python"]
#         ["Python", "SQL"] -> ["Python", "SQL"]
#         {"name": "Python"} -> [{"name": "Python"}]
#     """

#     if value is None:
#         return []

#     if isinstance(value, list):
#         return value

#     return [value]

# def safe_dict(value) -> dict:
#     """
#     Convert an extracted value into a safe dictionary.

#     Input:
#         value -> GPT extracted value.

#     Output:
#         Dictionary. Invalid values become {}.
#     """

#     return value if isinstance(value, dict) else {}
# def safe_float(value):
#     """
#     Convert AI-extracted experience values into a PostgreSQL-safe float.

#     Input:
#         value -> AI-extracted value such as:
#                  5
#                  "5"
#                  "5 years"
#                  "14+"
#                  "6-10"
#                  "Not provided"
#                  None

#     Output:
#         float or None
#     """
#     if value is None:
#         return None

#     if isinstance(value, (int, float)):
#         return float(value)

#     text = str(value).strip().lower()

#     if not text or text in {
#         "not provided",
#         "not specified",
#         "unknown",
#         "n/a",
#         "na",
#         "none",
#         "null",
#         "-"
#     }:
#         return None

#     # Handle ranges such as "6-10"
#     range_match = re.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)", text)
#     if range_match:
#         low = float(range_match.group(1))
#         high = float(range_match.group(2))
#         return (low + high) / 2

#     # Handle values such as "14+", "5 years", "3.5 years"
#     number_match = re.search(r"\d+(?:\.\d+)?", text)

#     if number_match:
#         return float(number_match.group())

#     return None
# ------------------------------------------------------------
# RESUME INGESTION
# ------------------------------------------------------------
# def store_resume(db: Session, path: str, drive_url: str | None = None) -> UUID:
#     """
#     Store one resume safely in PostgreSQL and Pinecone.

#     Input:
#         db   -> SQLAlchemy PostgreSQL session
#         path -> Resume file path

#     Output:
#         Candidate UUID.

#     Processing:
#         1. Detect duplicate resume.
#         2. Read resume text.
#         3. Extract candidate information using GPT.
#         4. If extraction fails, use safe fallback data.
#         5. Store candidate and resume in PostgreSQL.
#         6. Store structured skills/experience/education/etc.
#         7. Create Pinecone embeddings when text is available.
#         8. Pinecone failure does not prevent PostgreSQL ingestion.
#     """

#     path_obj = Path(path)

#     # ---------------------------------------------------------
#     # 1. Calculate file hash
#     # ---------------------------------------------------------

#     digest = file_hash(path)

#     existing = db.scalar(
#         select(Resume).where(
#             Resume.file_hash == digest
#         )
#     )

#     if existing:
#         return existing.candidate_id

#     # ---------------------------------------------------------
#     # 2. Read resume
#     # ---------------------------------------------------------

#     try:
#         text = read_file(path)
#     except Exception as error:
#         print(
#             f"   [WARNING] Could not extract text: {error}"
#         )

#         # We still ingest the resume.
#         text = ""
#     if text.strip() and looks_like_job_description(
#         text,
#         path_obj.name
#     ):
#         raise ValueError(
#             "File appears to be a Job Description, not a resume"
#         )
#     # ---------------------------------------------------------
#     # 3. Extract resume information
#     # ---------------------------------------------------------

#     data = {}

#     if text.strip():

#         try:
#             extracted = extract_resume(text)

#             if isinstance(extracted, dict):
#                 data = extracted
#             else:
#                 print(
#                     "   [WARNING] GPT returned invalid resume data."
#                 )

#         except Exception as error:
#             print(
#                 f"   [WARNING] Resume extraction failed: {error}"
#             )

#     # ---------------------------------------------------------
#     # 4. Safe candidate values
#     # ---------------------------------------------------------

#     candidate_name = (
#         data.get("name")
#         or path_obj.stem
#         or "Unknown Candidate"
#     )

#     candidate_name = str(candidate_name).strip()

#     if not candidate_name:
#         candidate_name = path_obj.stem or "Unknown Candidate"

#     # ---------------------------------------------------------
#     # 5. Create Candidate
#     # ---------------------------------------------------------

#     candidate = Candidate(
#     name=candidate_name,
#     email=data.get("email"),
#     phone=data.get("phone"),
#     location=data.get("location"),
#     total_experience_years=safe_float(
#         data.get("total_experience_years")
#     ),
#     current_company=data.get("current_company"),
#     current_role=data.get("current_role"),
#     notice_period_days=safe_float(
#         data.get("notice_period_days")
#     ),
#     profile_summary=data.get("profile_summary"),
#     raw_profile_text=text,
#     normalized_profile=data,
# )

#     db.add(candidate)
#     db.flush()

#     # ---------------------------------------------------------
#     # 6. Create Resume record
#     # ---------------------------------------------------------

#     resume = Resume(
#         candidate_id=candidate.id,
#         file_name=path_obj.name,
#         file_url=drive_url if drive_url else str(path_obj),
#         file_type=path_obj.suffix.lower().lstrip("."),
#         file_size=path_obj.stat().st_size,
#         file_hash=digest,
#         raw_text=text,
#         parsed_data=data,
#         parsing_status="COMPLETED",
#         extraction_status="COMPLETED",
#         extraction_model=settings.EXTRACTION_MODEL,
#         extraction_version="v1",
#     )

#     db.add(resume)
#     db.flush()

#     # ---------------------------------------------------------
#     # 7. Store skills safely
#     # ---------------------------------------------------------

#     skills = safe_list(
#         data.get("skills")
#     )

#     for item in skills:

#         if isinstance(item, dict):

#             name = item.get("name")

#             if not name:
#                 continue

#             normalized, parent, category = normalize_skill(
#                 name
#             )

#             if not normalized:
#                 continue

#             db.add(
#                 CandidateSkill(
#                     candidate_id=candidate.id,
#                     skill_name=str(name),
#                     normalized_skill_name=normalized,
#                     parent_skill=(
#                         item.get("parent_skill")
#                         or parent
#                     ),
#                     skill_category=(
#                         item.get("category")
#                         or category
#                     ),
#                     experience_years=item.get(
#                         "experience_years"
#                     ),
#                     proficiency=item.get(
#                         "proficiency"
#                     ),
#                     source="resume",
#                     confidence_score=item.get(
#                         "confidence_score"
#                     ),
#                 )
#             )

#         elif isinstance(item, str):

#             normalized, parent, category = normalize_skill(
#                 item
#             )

#             if not normalized:
#                 continue

#             db.add(
#                 CandidateSkill(
#                     candidate_id=candidate.id,
#                     skill_name=item.strip(),
#                     normalized_skill_name=normalized,
#                     parent_skill=parent,
#                     skill_category=category,
#                     source="resume",
#                 )
#             )

#     # ---------------------------------------------------------
#     # 8. Store experience safely
#     # ---------------------------------------------------------

#     experiences = safe_list(
#         data.get("experiences")
#         or data.get("experience")
#     )

#     for item in experiences:

#         if isinstance(item, str):
#             item = {
#                 "description": item
#             }

#         if not isinstance(item, dict):
#             continue

#         db.add(
#             CandidateExperience(
#                 candidate_id=candidate.id,
#                 company_name=item.get(
#                     "company_name"
#                 ),
#                 job_title=item.get(
#                     "job_title"
#                 ),
#                 employment_type=item.get(
#                     "employment_type"
#                 ),
#                 description=item.get(
#                     "description"
#                 ),
#                 domain=item.get(
#                     "domain"
#                 ),
#                 normalized_data=item,
#             )
#         )

#     # ---------------------------------------------------------
#     # 9. Store education safely
#     # ---------------------------------------------------------

#     education = safe_list(
#         data.get("education")
#     )

#     for item in education:

#         if isinstance(item, str):
#             item = {
#                 "degree": item
#             }

#         if not isinstance(item, dict):
#             continue

#         db.add(
#             CandidateEducation(
#                 candidate_id=candidate.id,
#                 degree=item.get(
#                     "degree"
#                 ),
#                 field_of_study=item.get(
#                     "field_of_study"
#                 ),
#                 institution=item.get(
#                     "institution"
#                 ),
#                 start_year=item.get(
#                     "start_year"
#                 ),
#                 end_year=item.get(
#                     "end_year"
#                 ),
#                 grade=item.get(
#                     "grade"
#                 ),
#             )
#         )

#     # ---------------------------------------------------------
#     # 10. Store certifications safely
#     # ---------------------------------------------------------

#     certifications = safe_list(
#         data.get("certifications")
#     )

#     for item in certifications:

#         if isinstance(item, str):
#             item = {
#                 "certification_name": item
#             }

#         if not isinstance(item, dict):
#             continue

#         certification_name = (
#             item.get("certification_name")
#             or item.get("name")
#         )

#         if not certification_name:
#             continue

#         db.add(
#             CandidateCertification(
#                 candidate_id=candidate.id,
#                 certification_name=certification_name,
#                 issuing_organization=(
#                     item.get(
#                         "issuing_organization"
#                     )
#                     or item.get("issuer")
#                 ),
#                 credential_id=item.get(
#                     "credential_id"
#                 ),
#             )
#         )

#     # ---------------------------------------------------------
#     # 11. Store projects safely
#     # ---------------------------------------------------------

#     projects = safe_list(
#         data.get("projects")
#     )

#     for item in projects:

#         if isinstance(item, str):
#             item = {
#                 "project_name": item
#             }

#         if not isinstance(item, dict):
#             continue

#         db.add(
#             CandidateProject(
#                 candidate_id=candidate.id,
#                 project_name=item.get(
#                     "project_name"
#                 ),
#                 description=item.get(
#                     "description"
#                 ),
#                 technologies=item.get(
#                     "technologies"
#                 ),
#                 domain=item.get(
#                     "domain"
#                 ),
#             )
#         )

#     # ---------------------------------------------------------
#     # 12. Commit PostgreSQL FIRST
#     # ---------------------------------------------------------

#     db.commit()

#     print("   [OK] PostgreSQL")
#     return candidate.id
# def looks_like_job_description(text: str, filename: str) -> bool:
#     """
#     Detect whether a file is more likely to be a Job Description than a resume.

#     Input:
#         text     -> extracted document text
#         filename -> original filename

#     Output:
#         True if the document appears to be a JD, otherwise False.
#     """
#     filename_lower = filename.lower()
#     text_lower = text.lower()

#     # Strong filename indicators
#     jd_filename_terms = [
#         "job description",
#         "job_description",
#         "jd_",
#         "_jd",
#         " jd",
#     ]

#     if any(term in filename_lower for term in jd_filename_terms):
#         return True

#     # Strong JD content indicators
#     jd_terms = [
#         "job description",
#         "role overview",
#         "role context",
#         "responsibilities",
#         "qualifications",
#         "requirements",
#         "key responsibilities",
#         "preferred qualifications",
#         "job requirements",
#     ]

#     matches = sum(1 for term in jd_terms if term in text_lower)

#     return matches >= 3

# # -------------------------------------------
# #     # ingest resume folder 
# # -------------------------------------------

# def ingest_resume_folder(db: Session, custom_dir: str | None = None, drive_url: str | None = None, file_url_map: dict | None = None) -> dict:
#     """
#     Ingest all resumes from a directory. and ingest every supported CV.

#     Input:
#         db -> SQLAlchemy PostgreSQL database session
#         custom_dir -> Optional path to scan instead of settings.RESUME_DIR
#         drive_url -> Optional Google Drive URL for the resume

#     Output:
#         Dictionary containing:
#         - total
#         - successful
#         - skipped
#         - failed
#         - failed_files

#     Processing:
#         1. Scan data/resumes.
#         2. Process every PDF/DOCX.
#         3. Store every readable or partially readable CV.
#         4. Continue even when extraction fails.
#         5. Continue even when Pinecone fails.
#     """

#     resume_dir = Path(custom_dir) if custom_dir else Path(settings.RESUME_DIR)

#     if not resume_dir.exists():

#         return {
#             "status": "FAILED",
#             "message": (
#                 f"Resume directory does not exist: "
#                 f"{resume_dir}"
#             ),
#             "total": 0,
#             "successful": 0,
#             "skipped": 0,
#             "failed": 0,
#             "failed_files": [],
#         }

#     files = sorted(
#         [
#             p
#             for p in resume_dir.rglob("*")
#             if p.is_file()
#             and p.suffix.lower() in {
#                 ".pdf",
#                 ".docx",
#                 ".txt",
#                 ".png",
#                 ".jpg",
#                 ".jpeg"
#             }
#         ],
#         key=lambda p: p.name.lower(),
#     )

#     total = len(files)

#     successful = 0
#     skipped = 0
#     failed = 0

#     failed_files = []

#     print()
#     print("=" * 70)
#     print(f"FOUND {total} RESUME FILES")
#     print("=" * 70)

#     for index, file_path in enumerate(
#         files,
#         start=1
#     ):

#         print(
#             f"\n[{index}/{total}] "
#             f"Processing: {file_path.name}"
#         )

#         try:

#             # -------------------------------------------------
#             # Duplicate check
#             # -------------------------------------------------

#             digest = file_hash(
#                 str(file_path)
#             )

#             existing = db.scalar(
#                 select(Resume).where(
#                     Resume.file_hash == digest
#                 )
#             )

#             if existing:

#                 print(
#                     "   [SKIPPED] Already ingested."
#                 )

#                 skipped += 1
#                 continue

#             # -------------------------------------------------
#             # Store resume
#             # -------------------------------------------------

#             # Use the per-file URL if available (Google Drive individual file URL),
#             # otherwise fall back to the folder URL.
#             per_file_url = None
#             if file_url_map:
#                 per_file_url = file_url_map.get(file_path.name)
#             if not per_file_url:
#                 per_file_url = drive_url

#             candidate_id = store_resume(
#                 db=db,
#                 path=str(file_path),
#                 drive_url=per_file_url
#             )

#             successful += 1

#             print(
#                 f"   [OK] Successfully ingested "
#                 f"| Candidate: {candidate_id}"
#             )

#         except ValueError as error:
#                 db.rollback()

#                 if "Job Description" in str(error):
#                     skipped += 1
#                     print(f"   [SKIPPED] {file_path.name} - Job Description detected.")
#                 else:
#                     failed += 1
#                     failed_files.append({
#                         "file": file_path.name,
#                         "error": str(error)
#                     })
#                     print(f"   [FAILED] {file_path.name}")
#                     print(f"   Reason: {error}")

#                 continue

#         except Exception as error:
#             db.rollback()
#             failed += 1
#             failed_files.append({
#                 "file": file_path.name,
#                 "error": str(error)
#             })
#             print(f"   [FAILED] {file_path.name}")
#             print(f"   Reason: {error}")
#             continue

#     # ---------------------------------------------------------
#     # Final summary
#     # ---------------------------------------------------------

#     print()
#     print("=" * 70)
#     print("RESUME INGESTION COMPLETE")
#     print("=" * 70)

#     print(
#         f"Total files : {total}"
#     )

#     print(
#         f"Successful  : {successful}"
#     )

#     print(
#         f"Skipped     : {skipped}"
#     )

#     print(
#         f"Failed      : {failed}"
#     )

#     if failed_files:

#         print()
#         print("FAILED FILES")
#         print("-" * 70)

#         for item in failed_files:

#             print(
#                 f"- {item['file']}"
#             )

#             print(
#                 f"  {item['error']}"
#             )

#     print("=" * 70)

#     return {
#         "status": "COMPLETED",
#         "total": total,
#         "successful": successful,
#         "skipped": skipped,
#         "failed": failed,
#         "failed_files": failed_files,
#     }

# def _get_gdrive_folder_file_map(folder_url: str) -> dict:
#     """
#     Return a mapping of {filename: individual_file_view_url} for all files
#     in a public Google Drive folder.

#     Uses gdown's internal folder-listing mechanism (same one it uses when
#     downloading folders) — no Google API key required.
#     Falls back to an empty dict gracefully if listing fails.
#     """
#     import re as _re

#     # Extract folder ID from URL like:
#     # https://drive.google.com/drive/folders/<FOLDER_ID>?usp=sharing
#     match = _re.search(r"/folders/([a-zA-Z0-9_-]+)", folder_url)
#     if not match:
#         print("[WARN] Could not extract folder ID from URL:", folder_url)
#         return {}

#     folder_id = match.group(1)
#     file_map = {}

#     # --- Strategy 1: Skipped (Incompatible with newer gdown versions) ---

#     # --- Strategy 2: parse Google Drive folder page HTML for file IDs ---
#     try:
#         import urllib.request as _req
#         import json as _json

#         page_url = f"https://drive.google.com/drive/folders/{folder_id}"
#         request = _req.Request(
#             page_url,
#             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
#         )
#         with _req.urlopen(request, timeout=15) as resp:
#             html = resp.read().decode("utf-8", errors="replace")

#         # Google Drive embeds file metadata as a JSON blob in the HTML.
#         # The pattern looks like: ["filename.pdf","file_id","application/pdf", ...]
#         # We extract all (name, id) pairs for PDF/DOCX files.
#         pattern = _re.compile(
#             r'"([^"]+\.(?:pdf|docx|doc|txt))","([a-zA-Z0-9_-]{25,})"',
#             _re.IGNORECASE,
#         )
#         for name, fid in pattern.findall(html):
#             if name not in file_map:
#                 file_map[name] = f"https://drive.google.com/file/d/{fid}/view"
#     except Exception as e2:
#         print(f"[WARN] HTML-parsing fallback failed: {e2}")

#     return file_map


# def sync_google_drive(db: Session, url: str) -> dict:
#     """
#     Sync resumes from a Google Drive URL.
#     Assuming the URL points to a shared Folder or a ZIP file.
#     """
#     temp_dir = tempfile.mkdtemp()
    
#     try:
#         if "drive.google.com/drive/folders/" in url:
#             # Fetch per-file URLs BEFORE downloading so we can map
#             # each local filename back to its individual Google Drive URL.
#             file_url_map = _get_gdrive_folder_file_map(url)
#             print(f"[Drive] Resolved {len(file_url_map)} individual file URLs.")

#             gdown.download_folder(url, output=temp_dir, quiet=False, use_cookies=False)
#             return ingest_resume_folder(
#                 db,
#                 custom_dir=temp_dir,
#                 drive_url=url,
#                 file_url_map=file_url_map if file_url_map else None,
#             )
#         else:
#             cwd = os.getcwd()
#             try:
#                 os.chdir(temp_dir)
#                 output_path = gdown.download(url, quiet=False)
                
#                 if output_path and zipfile.is_zipfile(output_path):
#                     with zipfile.ZipFile(output_path, 'r') as zip_ref:
#                         zip_ref.extractall(temp_dir)
#                     os.remove(output_path)
#             finally:
#                 os.chdir(cwd)
            
#             return ingest_resume_folder(db, custom_dir=temp_dir, drive_url=url)
#     except Exception as e:
#         return {
#             "status": "FAILED",
#             "message": f"Failed to download or process Google Drive link: {str(e)}",
#             "total": 0, "successful": 0, "skipped": 0, "failed": 0, "failed_files": []
#         }
#     finally:
#         shutil.rmtree(temp_dir, ignore_errors=True)
# ------------------------------------------------------------
# JD CREATION
# ------------------------------------------------------------
# def create_job(
#     db: Session,
#     user_id: UUID,
#     raw_text: str,
#     file_name: str | None = None,
#     file_path: str | None = None
# ) -> Job:
#     """
#     Create a Job from either written JD text or an uploaded JD file.

#     Input:
#         db        -> PostgreSQL database session
#         user_id   -> authenticated recruiter/user UUID
#         raw_text  -> JD text
#         file_name -> optional uploaded JD filename
#         file_path -> optional path of uploaded JD file

#     Output:
#         Persisted Job with JobRequirement and AIExtractionLog.
#     """

#     def _safe_float(val):
#         try:
#             if isinstance(val, dict):
#                 val = val.get("max", val.get("min", val.get("value", None)))
#             return float(val) if val is not None else None
#         except (ValueError, TypeError):
#             return None

#     def _safe_int(val):
#         try:
#             if isinstance(val, dict):
#                 val = val.get("max", val.get("min", val.get("value", None)))
#             return int(float(val)) if val is not None else None
#         except (ValueError, TypeError):
#             return None

#     if not raw_text or not raw_text.strip():
#         raise ValueError("JD content cannot be empty")

#     raw_text = raw_text.strip()

#     # --------------------------------------------------------
#     # 1. Extract JD requirements using GPT
#     # --------------------------------------------------------
#     data = extract_jd(raw_text)

#     # --------------------------------------------------------
#     # 2. Create Job
#     # --------------------------------------------------------
#     job = Job(
#         created_by=user_id,
#         title=data.get("job_title") or "Untitled Job",
#         description=raw_text,
#         location=data.get("location"),
#         work_mode=data.get("work_mode"),
#         jd_file_name=file_name,
#         jd_file_url=file_path,
#         jd_raw_text=raw_text,
#         status="READY"
#     )

#     db.add(job)
#     db.flush()

#     # --------------------------------------------------------
#     # 3. Store extracted JD requirements
#     # --------------------------------------------------------
#     req = JobRequirement(
#         job_id=job.id,
#         job_title=data.get("job_title"),

#         minimum_experience=_safe_float(data.get("min_experience_years")),
#         maximum_experience=_safe_float(data.get("max_experience_years")),

#         location=data.get("location") if isinstance(data.get("location"), str) else None,
#         work_mode=data.get("work_mode") if isinstance(data.get("work_mode"), str) else None,
#         notice_period_days=_safe_int(data.get("notice_period_days")),

#         mandatory_skills=data.get("mandatory_skills") or [],
#         preferred_skills=data.get("preferred_skills") or [],

#         education=data.get("education") or [],
#         certifications=data.get("certifications") or [],
#         domains=data.get("domains") or [],
#         responsibilities=data.get("responsibilities") or [],

#         other_requirements=data.get("other_requirements") or [],

#         extraction_model=settings.EXTRACTION_MODEL,
#         extraction_version="v1",
#         confidence_score=safe_float(data.get("confidence_score"))
#     )

#     db.add(req)

#     # --------------------------------------------------------
#     # 4. Store AI extraction log
#     # --------------------------------------------------------
#     db.add(
#         AIExtractionLog(
#             entity_type="JD",
#             entity_id=job.id,
#             model_name=settings.EXTRACTION_MODEL,
#             prompt_version="v1",
#             input_text_hash=hashlib.sha256(
#                 raw_text.encode()
#             ).hexdigest(),
#             output_data=data,
#             confidence_score=safe_float(data.get("confidence_score")),
#             validation_status="PASSED"
#         )
#     )

#     # --------------------------------------------------------
#     # 5. Save everything
#     # --------------------------------------------------------
#     db.commit()
#     db.refresh(job)

#     return job

# ------------------------------------------------------------
# MATCHING + EVIDENCE
# ------------------------------------------------------------


# def exact_skill_match(db: Session, candidate_id: UUID, required: list) -> dict:
#     """Input: candidate and JD required skills. Output: per-skill match evidence and percentage."""
#     skills = db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id)).all()
#     normalized = {s.normalized_skill_name.lower(): s for s in skills}
#     parent_map = {s.parent_skill.lower(): s for s in skills if s.parent_skill}
#     details, matched = [], 0
#     required_names = [x.get("name") if isinstance(x, dict) else str(x) for x in required]
#     for req in required_names:
#         key = req.lower()
#         if key in normalized:
#             matched += 1; details.append({"required": req, "status": "EXACT", "candidate_skill": normalized[key].skill_name})
#         elif key in parent_map:
#             details.append({"required": req, "status": "PARENT_SUPPORT", "candidate_skill": parent_map[key].skill_name})
#         else:
#             details.append({"required": req, "status": "MISSING"})
#     return {"matched": matched, "total": len(required_names), "details": details}


# def exact_skill_match(db: Session, candidate_id: UUID, required: list) -> dict:

#     """

#     Match JD-required skills against candidate skills.
 
#     Uses database-normalized skill names and parent skills.

#     No hardcoded skill aliases.
 
#     Match priority:

#         EXACT > PARENT_SUPPORT > MISSING
 
#     Only EXACT matches count toward the percentage.

#     """
 
#     # Get candidate skills

#     skills = db.scalars(

#         select(CandidateSkill).where(

#             CandidateSkill.candidate_id == candidate_id

#         )

#     ).all()
 
#     # Prepare candidate skills from DB

#     candidate_skills = []
 
#     for skill in skills:

#         normalized = (skill.normalized_skill_name or skill.skill_name or "").strip().lower()

#         original = (skill.skill_name or "").strip()

#         parent = (skill.parent_skill or "").strip().lower()
 
#         candidate_skills.append({

#             "normalized": normalized,

#             "original": original,

#             "parent": parent,

#         })
 
#     # Extract required skill names

#     required_names = [

#         x.get("name") if isinstance(x, dict) else str(x)

#         for x in required

#     ]
 
#     details = []

#     matched = 0
 
#     for req in required_names:
 
#         required_skill = str(req).strip().lower()
 
#         status = "MISSING"

#         matched_skill_name = None
 
#         # ---------------------------------------------------------

#         # 1. EXACT NORMALIZED MATCH

#         # ---------------------------------------------------------

#         for candidate in candidate_skills:
 
#             if required_skill == candidate["normalized"]:

#                 status = "EXACT"

#                 matched_skill_name = candidate["original"]

#                 break
 
#         # ---------------------------------------------------------

#         # 2. PARENT SKILL MATCH

#         # ---------------------------------------------------------

#         if status == "MISSING":
 
#             for candidate in candidate_skills:
 
#                 if (

#                     candidate["parent"]

#                     and required_skill == candidate["parent"]

#                 ):

#                     status = "PARENT_SUPPORT"

#                     matched_skill_name = candidate["original"]

#                     break
 
#         # Only exact matches count

#         if status == "EXACT":

#             matched += 1
 
#         details.append({

#             "required": req,

#             "status": status,

#             "candidate_skill": matched_skill_name,

#         })
 
#     # Calculate percentage

#     total = len(required_names)
 
#     percentage = (

#         round((matched / total) * 100, 2)

#         if total > 0

#         else 0

#     )
 
#     return {

#         "matched": matched,

#         "total": total,

#         "percentage": percentage,

#         "details": details,

#     }
 
# def retrieve_evidence(db: Session, candidate_id: UUID) -> list[dict]:
#     """Input: candidate UUID. Output: profile summary from PostgreSQL as evidence."""
#     candidate = db.get(Candidate, candidate_id)
#     if candidate and candidate.profile_summary:
#         return [{"score": 1.0, "text": candidate.profile_summary}]
#     return [{"score": 0.0, "text": "No evidence available."}]

# # ------------------------------------------------------------
# # CANDIDATE SEARCH
# # ------------------------------------------------------------
# def structured_candidate_search(
#     db: Session,
#     req: JobRequirement,
# ) -> list[UUID]:
#     """
#     Deterministic structured candidate filtering.

#     No LLM. No generated SQL.
#     Filters on: experience, notice period.
#     Location is intentionally excluded — it is scored in calculate_normal_score().

#     Candidates with NULL experience or NULL notice period are always allowed
#     through so that incomplete resumes are not silently discarded.

#     Input:
#         db  -> SQLAlchemy PostgreSQL session
#         req -> JobRequirement with structured JD fields

#     Output:
#         List of candidate UUIDs that pass the structured filters.
#     """

#     query = select(Candidate.id)

#     conditions = []

#     # ---------------------------------------------------------
#     # EXPERIENCE
#     # Candidates with NULL experience pass through; they will
#     # receive a partial score in the normal scoring stage.
#     # ---------------------------------------------------------
#     if req.minimum_experience is not None:
#         conditions.append(
#             or_(
#                 Candidate.total_experience_years.is_(None),
#                 Candidate.total_experience_years >= req.minimum_experience,
#             )
#         )

#     if req.maximum_experience is not None:
#         conditions.append(
#             or_(
#                 Candidate.total_experience_years.is_(None),
#                 Candidate.total_experience_years <= req.maximum_experience,
#             )
#         )

#     # ---------------------------------------------------------
#     # NOTICE PERIOD
#     # Candidates with NULL notice period pass through.
#     # ---------------------------------------------------------
#     if req.notice_period_days is not None:
#         conditions.append(
#             or_(
#                 Candidate.notice_period_days.is_(None),
#                 Candidate.notice_period_days <= req.notice_period_days,
#             )
#         )

#     if conditions:
#         query = query.where(and_(*conditions))

#     rows = db.execute(query).all()

#     return [UUID(str(row[0])) for row in rows]



# def fts_candidate_search(
#     db: Session,
#     req: JobRequirement,
#     candidate_ids: list[UUID],
# ) -> list[UUID]:
#     """
#     PostgreSQL Full Text Search on resume raw_text.

#     Only uses short keyword terms (mandatory skills, preferred skills, domains).
#     Responsibilities are intentionally excluded — they are long sentences that
#     cause plainto_tsquery to require every word, producing zero matches.

#     If FTS returns 0 matches, falls back to the full structured search pool
#     so that candidates are never silently discarded before normal scoring.

#     Input:
#         db            -> SQLAlchemy PostgreSQL session
#         req           -> JobRequirement with skill/domain lists
#         candidate_ids -> pool of candidate UUIDs to search within

#     Output:
#         Ordered list of candidate UUIDs sorted by FTS rank (best first).
#         Falls back to candidate_ids if no search terms or no FTS matches.
#     """

#     search_terms = []

#     # Only short keyword terms — skills and domains.
#     # Responsibilities are long sentences and must NOT be included here.
#     if req.mandatory_skills:
#         search_terms.extend(
#             str(skill) for skill in req.mandatory_skills if skill
#         )

#     if req.preferred_skills:
#         search_terms.extend(
#             str(skill) for skill in req.preferred_skills if skill
#         )

#     if req.domains:
#         search_terms.extend(
#             str(domain) for domain in req.domains if domain
#         )

#     if not search_terms:
#         # No searchable terms — return full pool unchanged.
#         return candidate_ids

#     # Build an OR-based FTS query so a candidate matches if ANY skill appears,
#     # not ALL of them. This avoids zero results when skills are diverse.
#     # Each term is sanitised and joined with the | (OR) operator.
#     def _clean_term(t: str) -> str:
#         # Remove characters that break to_tsquery syntax.
#         return re.sub(r"[^\w\s]", " ", t).strip()

#     or_terms = []
#     for term in search_terms:
#         cleaned = _clean_term(term)
#         if cleaned:
#             # Multi-word skill (e.g. "Machine Learning") → phrase match.
#             words = cleaned.split()
#             if len(words) > 1:
#                 or_terms.append(" <-> ".join(words))
#             else:
#                 or_terms.append(words[0])

#     if not or_terms:
#         return candidate_ids

#     ts_query_str = " | ".join(or_terms)

#     ts_query = func.to_tsquery("english", ts_query_str)

#     query = (
#         select(
#             Resume.candidate_id,
#             func.ts_rank(Resume.search_vector, ts_query).label("rank"),
#         )
#         .where(Resume.candidate_id.in_(candidate_ids))
#         .where(Resume.search_vector.op("@@")(ts_query))
#         .order_by(text("rank DESC"))
#     )

#     try:
#         rows = db.execute(query).all()
#     except Exception as fts_error:
#         # If the FTS query fails for any reason, fall back to the full pool.
#         print(f"[FTS] Query failed ({fts_error}), falling back to full pool.")
#         return candidate_ids

#     matched_ids = [UUID(str(row[0])) for row in rows]

#     if not matched_ids:
#         # FTS found no matches — fall back to the full structured pool so
#         # normal scoring can still evaluate all candidates.
#         print("[FTS] No FTS matches found, falling back to full structured pool.")
#         return candidate_ids

#     return matched_ids



# # ------------------------------------------------------------
# # GPT EVALUATION
# # ------------------------------------------------------------
# def ai_score_candidate(payload: dict) -> dict:
#     """Output: precisely 8 numerical scores and reasoning string."""
#     prompt = f"""
# You are an expert AI Recruiter evaluating a candidate against a job description.
# Assign precise numerical scores for each of the following 8 criteria, adhering strictly to the maximum points allowed for each.

# Criteria & Maximum Points:
# 1. mandatory_skills_score: max 30
# 2. experience_score: max 25
# 3. domain_score: max 15
# 4. preferred_skills_score: max 10
# 5. education_score: max 5
# 6. location_score: max 5
# 7. availability_score: max 5
# 8. other_requirements_score: max 5

# Rules:
# - Be realistic and precise. Give partial points if they partially meet a requirement.
# - If the JD does not mention a requirement (e.g., no location specified), award full points for that category.
# - Output ONLY a JSON object with EXACTLY the keys listed above (as numbers), plus a string key 'reasoning' explaining the scores briefly.
# DATA:\n{json.dumps(payload, default=str)}
# """
#     return _json_completion(prompt, settings.EVALUATION_MODEL)

# # ------------------------------------------------------------
# # DETERMINISTIC SCORING
# # ------------------------------------------------------------
# def calculate_score(evaluation: dict) -> dict:
#     """Input: evaluation dict with 8 numeric scores from LLM. Output: fixed 100-point score and classification."""
#     try:
#         mandatory = float(evaluation.get("mandatory_skills_score", 0))
#         experience = float(evaluation.get("experience_score", 0))
#         domain = float(evaluation.get("domain_score", 0))
#         preferred = float(evaluation.get("preferred_skills_score", 0))
#         education = float(evaluation.get("education_score", 0))
#         location = float(evaluation.get("location_score", 0))
#         availability = float(evaluation.get("availability_score", 0))
#         other = float(evaluation.get("other_requirements_score", 0))
#     except (ValueError, TypeError):
#         mandatory, experience, domain, preferred, education, location, availability, other = 0,0,0,0,0,0,0,0
#     total = round(mandatory + experience + domain + preferred + education + location + availability + other, 2)
#     if total >= 90: classification = "EXCELLENT_MATCH"
#     elif total >= 80: classification = "STRONG_MATCH"
#     elif total >= 70: classification = "GOOD_MATCH"
#     elif total >= 60: classification = "MODERATE_MATCH"
#     else: classification = "LOW_MATCH_DO_NOT_PRIORITIZE"
#     return {"mandatory_skills_score": mandatory, "experience_score": experience, "domain_score": domain,
#             "preferred_skills_score": preferred, "education_score": education, "location_score": location,
#             "availability_score": availability, "other_requirements_score": other, "total_score": total,
#             "classification": classification}


# def calculate_normal_score(
#     candidate: Candidate,
#     req: JobRequirement,
#     skills_map: dict,
#     experiences_map: dict,
#     educations_map: dict,
#     projects_map: dict,
# ) -> dict:
#     """
#     Deterministic 100-point candidate scoring.

#     Uses pre-fetched, bulk-loaded data from PostgreSQL to avoid N+1 queries.
#     No LLM calls.

#     Scoring breakdown:
#         1. Mandatory Skills   = 30
#         2. Experience         = 25
#         3. Domain Knowledge   = 15
#         4. Preferred Skills   = 10
#         5. Education          =  5
#         6. Location           =  5
#         7. Availability       =  5
#         8. Other Requirements =  5
#                                ---
#                                100

#     Input:
#         candidate      -> Candidate ORM object
#         req            -> JobRequirement ORM object
#         skills_map     -> {candidate_id: [CandidateSkill, ...]}
#         experiences_map-> {candidate_id: [CandidateExperience, ...]}
#         educations_map -> {candidate_id: [CandidateEducation, ...]}
#         projects_map   -> {candidate_id: [CandidateProject, ...]}

#     Output:
#         Dict with all 8 component scores, total_score, classification.
#     """

#     candidate_skills = skills_map.get(candidate.id, [])
#     candidate_experiences = experiences_map.get(candidate.id, [])
#     candidate_educations = educations_map.get(candidate.id, [])
#     candidate_projects = projects_map.get(candidate.id, [])

#     # Build candidate skill name set (lowercase) from all skill columns
#     candidate_skill_names: set[str] = set()
#     for skill in candidate_skills:
#         if skill.normalized_skill_name:
#             candidate_skill_names.add(str(skill.normalized_skill_name).strip().lower())
#         if skill.skill_name:
#             candidate_skill_names.add(str(skill.skill_name).strip().lower())
#         if skill.parent_skill:
#             candidate_skill_names.add(str(skill.parent_skill).strip().lower())

#     # =========================================================
#     # 1. MANDATORY SKILLS — 30
#     # =========================================================
#     mandatory_skills = [
#         str(x).strip().lower() for x in (req.mandatory_skills or []) if x
#     ]

#     if not mandatory_skills:
#         mandatory_score = 30.0
#     else:
#         matched = 0
#         for required in mandatory_skills:
#             if required in candidate_skill_names:
#                 matched += 1
#                 continue
#             # Basic containment fallback
#             if any(
#                 required in cs or cs in required
#                 for cs in candidate_skill_names
#             ):
#                 matched += 1
#         mandatory_score = (matched / len(mandatory_skills)) * 30

#     # =========================================================
#     # 2. EXPERIENCE — 25
#     # =========================================================
#     experience_score = 0.0
#     candidate_exp = candidate.total_experience_years

#     if candidate_exp is not None:
#         candidate_exp = float(candidate_exp)
#         min_exp = req.minimum_experience
#         max_exp = req.maximum_experience

#         if min_exp is None and max_exp is None:
#             experience_score = 25.0
#         elif min_exp is not None and max_exp is not None:
#             if float(min_exp) <= candidate_exp <= float(max_exp):
#                 experience_score = 25.0
#             elif candidate_exp < float(min_exp):
#                 ratio = candidate_exp / float(min_exp)
#                 experience_score = max(0.0, min(25.0, ratio * 25))
#             else:
#                 excess = candidate_exp - float(max_exp)
#                 if excess <= 2:
#                     experience_score = 20.0
#                 elif excess <= 5:
#                     experience_score = 15.0
#                 else:
#                     experience_score = 10.0
#         elif min_exp is not None:
#             if candidate_exp >= float(min_exp):
#                 experience_score = 25.0
#             else:
#                 experience_score = (candidate_exp / float(min_exp)) * 25
#         elif max_exp is not None:
#             experience_score = 25.0 if candidate_exp <= float(max_exp) else 15.0

#     # =========================================================
#     # 3. DOMAIN KNOWLEDGE — 15
#     # =========================================================
#     required_domains = [
#         str(x).strip().lower() for x in (req.domains or []) if x
#     ]

#     if not required_domains:
#         domain_score = 15.0
#     else:
#         domain_text_parts = []
#         for exp in candidate_experiences:
#             if exp.job_title:
#                 domain_text_parts.append(str(exp.job_title))
#             if getattr(exp, "company_name", None):
#                 domain_text_parts.append(str(exp.company_name))
#             if getattr(exp, "description", None):
#                 domain_text_parts.append(str(exp.description))
#         for project in candidate_projects:
#             if getattr(project, "domain", None):
#                 domain_text_parts.append(str(project.domain))
#             if getattr(project, "description", None):
#                 domain_text_parts.append(str(project.description))

#         domain_text = " ".join(domain_text_parts).lower()
#         matched_domains = sum(1 for d in required_domains if d in domain_text)
#         domain_score = (matched_domains / len(required_domains)) * 15

#     # =========================================================
#     # 4. PREFERRED SKILLS — 10
#     # =========================================================
#     preferred_skills = [
#         str(x).strip().lower() for x in (req.preferred_skills or []) if x
#     ]

#     if not preferred_skills:
#         preferred_score = 10.0
#     else:
#         matched = 0
#         for required in preferred_skills:
#             if required in candidate_skill_names:
#                 matched += 1
#                 continue
#             if any(
#                 required in cs or cs in required
#                 for cs in candidate_skill_names
#             ):
#                 matched += 1
#         preferred_score = (matched / len(preferred_skills)) * 10

#     # =========================================================
#     # 5. EDUCATION — 5
#     # =========================================================
#     if not req.education:
#         education_score = 5.0
#     else:
#         education_text = " ".join(
#             filter(
#                 None,
#                 [str(getattr(row, "degree", "")) for row in candidate_educations]
#                 + [str(getattr(row, "field_of_study", "")) for row in candidate_educations],
#             )
#         ).lower()

#         # req.education can be a list or a string
#         if isinstance(req.education, list):
#             req_education_str = " ".join(str(e) for e in req.education).lower()
#         else:
#             req_education_str = str(req.education).lower()

#         education_score = 5.0 if req_education_str and req_education_str in education_text else 0.0

#     # =========================================================
#     # 6. LOCATION — 5
#     # =========================================================
#     if not req.location:
#         location_score = 5.0
#     elif candidate.location:
#         location_score = (
#             5.0
#             if str(req.location).strip().lower() in str(candidate.location).strip().lower()
#             else 0.0
#         )
#     else:
#         location_score = 0.0

#     # =========================================================
#     # 7. AVAILABILITY / NOTICE PERIOD — 5
#     # =========================================================
#     if req.notice_period_days is None:
#         availability_score = 5.0
#     elif candidate.notice_period_days is not None:
#         availability_score = (
#             5.0
#             if float(candidate.notice_period_days) <= float(req.notice_period_days)
#             else 0.0
#         )
#     else:
#         availability_score = 0.0

#     # =========================================================
#     # 8. OTHER REQUIREMENTS — 5
#     # =========================================================
#     other_requirements = req.other_requirements

#     if not other_requirements:
#         other_score = 5.0
#     else:
#         candidate_text = (
#             f"{candidate.profile_summary or ''} "
#             f"{candidate.current_role or ''} "
#             f"{candidate.current_company or ''}"
#         ).lower()

#         if isinstance(other_requirements, list):
#             valid_requirements = [str(x).strip().lower() for x in other_requirements if x]
#         else:
#             valid_requirements = [str(other_requirements).strip().lower()]

#         if not valid_requirements:
#             other_score = 5.0
#         else:
#             matched = sum(1 for r in valid_requirements if r in candidate_text)
#             other_score = (matched / len(valid_requirements)) * 5

#     # =========================================================
#     # TOTAL & CLASSIFICATION
#     # =========================================================
#     total = round(
#         mandatory_score + experience_score + domain_score + preferred_score
#         + education_score + location_score + availability_score + other_score,
#         2,
#     )

#     if total >= 90:
#         classification = "EXCELLENT_MATCH"
#     elif total >= 80:
#         classification = "STRONG_MATCH"
#     elif total >= 70:
#         classification = "GOOD_MATCH"
#     elif total >= 60:
#         classification = "MODERATE_MATCH"
#     else:
#         classification = "LOW_MATCH_DO_NOT_PRIORITIZE"

#     return {
#         "mandatory_skills_score": round(mandatory_score, 2),
#         "experience_score": round(experience_score, 2),
#         "domain_score": round(domain_score, 2),
#         "preferred_skills_score": round(preferred_score, 2),
#         "education_score": round(education_score, 2),
#         "location_score": round(location_score, 2),
#         "availability_score": round(availability_score, 2),
#         "other_requirements_score": round(other_score, 2),
#         "total_score": total,
#         "classification": classification,
#     }


# ------------------------------------------------------------
# SCREENING ORCHESTRATION
# ------------------------------------------------------------
# def screen_job(db: Session, job_id: UUID) -> dict:
#     """
#     Multi-stage screening pipeline.

#     Stage 1 — Structured Search:  experience / location / notice period  (SQL, no LLM)
#     Stage 2 — FTS:                mandatory & preferred skills, domains    (PostgreSQL FTS, no LLM)
#     Stage 3 — Normal Scoring:     deterministic 100-point score            (Python, no LLM)
#     Stage 4 — Top 30 → LLM:       deep evaluation only on best candidates  (LLM)
#     Stage 5 — Final Ranking:      persist ranked results
#     """
#     job = db.get(Job, job_id)
#     if not job or not job.requirements:
#         raise ValueError("Job or extracted requirements not found")

#     req = job.requirements

#     run = ScreeningRun(
#         job_id=job.id,
#         status="RUNNING",
#         current_stage="SEARCHING",
#         started_at=time_now(),
#     )
#     db.add(run)
#     job.status = "SEARCHING"
#     db.commit()

#     try:

#         # =====================================================
#         # STEP 1 — STRUCTURED SEARCH
#         # =====================================================
#         candidate_ids = structured_candidate_search(db, req)

#         print(f"[SEARCH] Structured search returned {len(candidate_ids)} candidates")

#         if candidate_ids:
#             s_cands = db.scalars(select(Candidate).where(Candidate.id.in_(candidate_ids))).all()
#             print("\n--- Candidates Passing Structured Search ---")
#             for c in s_cands:
#                 print(f"Candidate Name: {c.name}")
#             print("--------------------------------------------\n")

#         # =====================================================
#         # STEP 2 — FTS
#         # =====================================================
#         if candidate_ids:
#             candidate_ids = fts_candidate_search(db, req, candidate_ids)

#         print(f"[SEARCH] FTS returned {len(candidate_ids)} candidates")

#         if candidate_ids:
#             f_cands = db.scalars(select(Candidate).where(Candidate.id.in_(candidate_ids))).all()
#             print("\n--- Candidates Passing FTS Search ---")
#             for c in f_cands:
#                 print(f"Candidate Name: {c.name}")
#             print("-------------------------------------\n")

#         if not candidate_ids:
#             print("No candidates found after search. Exiting.")
#             run.status = "COMPLETED"
#             run.current_stage = "COMPLETED"
#             run.completed_at = time_now()
#             job.status = "ACTIVE"
#             db.commit()
#             return {"job_id": str(job.id), "candidates_evaluated": 0, "normal_scored": 0, "llm_scored": 0, "top_10": []}

#         # =====================================================
#         # STEP 3 — BULK FETCH (avoids N+1 in normal scoring)
#         # =====================================================
#         run.total_candidates = len(candidate_ids)
#         run.current_stage = "SCORING"
#         db.commit()

#         candidates = db.scalars(
#             select(Candidate).where(Candidate.id.in_(candidate_ids))
#         ).all()

#         candidate_map: dict = {c.id: c for c in candidates}

#         all_skills = db.scalars(
#             select(CandidateSkill).where(CandidateSkill.candidate_id.in_(candidate_ids))
#         ).all()
#         skills_map: dict = {}
#         for s in all_skills:
#             skills_map.setdefault(s.candidate_id, []).append(s)

#         all_experiences = db.scalars(
#             select(CandidateExperience).where(CandidateExperience.candidate_id.in_(candidate_ids))
#         ).all()
#         experiences_map: dict = {}
#         for e in all_experiences:
#             experiences_map.setdefault(e.candidate_id, []).append(e)

#         all_educations = db.scalars(
#             select(CandidateEducation).where(CandidateEducation.candidate_id.in_(candidate_ids))
#         ).all()
#         educations_map: dict = {}
#         for ed in all_educations:
#             educations_map.setdefault(ed.candidate_id, []).append(ed)

#         all_projects = db.scalars(
#             select(CandidateProject).where(CandidateProject.candidate_id.in_(candidate_ids))
#         ).all()
#         projects_map: dict = {}
#         for p in all_projects:
#             projects_map.setdefault(p.candidate_id, []).append(p)

#         # =====================================================
#         # STEP 4 — NORMAL / DETERMINISTIC SCORING
#         # =====================================================
#         normal_ranked: list[tuple[UUID, dict]] = []

#         for cid in candidate_ids:
#             candidate = candidate_map.get(cid)
#             if not candidate:
#                 continue
#             try:
#                 score = calculate_normal_score(
#                     candidate=candidate,
#                     req=req,
#                     skills_map=skills_map,
#                     experiences_map=experiences_map,
#                     educations_map=educations_map,
#                     projects_map=projects_map,
#                 )
#                 normal_ranked.append((cid, score))
#             except Exception as error:
#                 print(f"Normal scoring failed for {cid}: {error}")

#         # =====================================================
#         # STEP 5 — SORT & SLICE TOP 30
#         # =====================================================
#         normal_ranked.sort(key=lambda item: item[1]["total_score"], reverse=True)
#         top_30 = normal_ranked[:30]

#         print(
#             f"[SCORING] {len(normal_ranked)} candidates scored. "
#             f"Sending top {len(top_30)} to LLM."
#         )

#         # =====================================================
#         # STEP 6 — LLM FINAL SCORING (Top 30 only)
#         # =====================================================
#         run.current_stage = "AI_EVALUATION"
#         db.commit()

#         import concurrent.futures

#         scoring_tasks: list[tuple[UUID, dict, dict]] = []

#         for cid, normal_score in top_30:
#             candidate = candidate_map.get(cid)
#             if not candidate:
#                 continue
#             payload = {
#                 "candidate": {
#                     "name": candidate.name,
#                     "experience": candidate.total_experience_years,
#                     "company": candidate.current_company,
#                     "role": candidate.current_role,
#                     "location": candidate.location,
#                     "notice_period_days": candidate.notice_period_days,
#                     "profile": candidate.profile_summary,
#                 },
#                 "requirements": {
#                     "min_experience": req.minimum_experience,
#                     "max_experience": req.maximum_experience,
#                     "mandatory_skills": req.mandatory_skills,
#                     "preferred_skills": req.preferred_skills,
#                     "education": req.education,
#                     "certifications": req.certifications,
#                     "domains": req.domains,
#                     "responsibilities": req.responsibilities,
#                     "location": req.location,
#                     "work_mode": req.work_mode,
#                     "notice_period_days": req.notice_period_days,
#                     "other_requirements": req.other_requirements,
#                 },
#                 "normal_score": normal_score,
#             }
#             scoring_tasks.append((cid, payload, normal_score))

#         final_ranked: list[tuple, dict] = []

#         with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
#             future_to_data = {
#                 executor.submit(ai_score_candidate, payload): (cid, normal_score)
#                 for cid, payload, normal_score in scoring_tasks
#             }

#             for future in concurrent.futures.as_completed(future_to_data):
#                 cid, normal_score = future_to_data[future]
#                 try:
#                     llm_evaluation = future.result()
#                     llm_score = calculate_score(llm_evaluation)

#                     # Persist final score
#                     jc = db.scalar(
#                         select(JobCandidate).where(
#                             JobCandidate.job_id == job.id,
#                             JobCandidate.candidate_id == cid,
#                         )
#                     )
#                     if not jc:
#                         jc = JobCandidate(job_id=job.id, candidate_id=cid)
#                         db.add(jc)
#                         db.flush()

#                     jc.eligibility_status = (
#                         "ELIGIBLE" if llm_score["total_score"] >= 60 else "INELIGIBLE"
#                     )
#                     jc.recruitment_status = "SCREENED"
#                     jc.overall_score = llm_score["total_score"]
#                     jc.classification = llm_score["classification"]

#                     result_record = db.scalar(
#                         select(ScreeningResult).where(
#                             ScreeningResult.job_candidate_id == jc.id
#                         )
#                     )
#                     if not result_record:
#                         result_record = ScreeningResult(
#                             job_candidate_id=jc.id,
#                             classification=llm_score["classification"],
#                         )
#                         db.add(result_record)

#                     for key in [
#                         "mandatory_skills_score",
#                         "experience_score",
#                         "domain_score",
#                         "preferred_skills_score",
#                         "education_score",
#                         "location_score",
#                         "availability_score",
#                         "other_requirements_score",
#                         "total_score",
#                         "classification",
#                     ]:
#                         setattr(result_record, key, llm_score[key])

#                     result_record.matching_details = {
#                         "normal_score": normal_score,
#                         "evaluation": llm_evaluation.get("reasoning"),
#                     }
#                     result_record.semantic_matches = []
#                     result_record.missing_requirements = []
#                     result_record.strengths = []
#                     result_record.concerns = []
#                     result_record.screening_model = settings.EVALUATION_MODEL
#                     result_record.screening_version = "v3"

#                     final_ranked.append((jc, llm_score))
#                     run.successful_candidates += 1

#                 except Exception as error:
#                     print(f"LLM scoring failed for {cid}: {error}")
#                     run.failed_candidates += 1

#                 run.processed_candidates += 1
#                 db.commit()

#         # =====================================================
#         # STEP 7 — FINAL SORT & RANKING
#         # =====================================================
#         final_ranked.sort(key=lambda item: item[1]["total_score"], reverse=True)

#         for position, (jc, score) in enumerate(final_ranked, 1):
#             jc.ranking_position = position
#             jc.is_shortlisted = position <= settings.TOP_N
#             db.add(jc)

#         job.status = "ACTIVE"
#         run.status = "COMPLETED"
#         run.current_stage = "COMPLETED"
#         run.completed_at = time_now()
#         db.commit()

#         return {
#             "job_id": str(job.id),
#             "candidates_evaluated": len(candidate_ids),
#             "normal_scored": len(normal_ranked),
#             "llm_scored": len(final_ranked),
#             "top_10": get_job_candidates(db, job.id, limit=settings.TOP_N),
#         }

#     except Exception as exc:
#         db.rollback()
#         run.status = "FAILED"
#         run.error_message = str(exc)
#         run.completed_at = time_now()
#         job.status = "DRAFT"
#         db.commit()
#         raise


def time_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)

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
        }

        if has_outreach:
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
                awaiting += 1

            # Determine delivery status from latest outbound contact log
            latest_contact = db.scalar(
                select(CandidateContact)
                .where(
                    CandidateContact.job_candidate_id == jc.id,
                    CandidateContact.message_type == "OUTBOUND",
                )
                .order_by(CandidateContact.created_at.desc())
                .limit(1)
            )

            c_status = (latest_contact.status if latest_contact else ("DELIVERED" if status in {"INTERESTED", "INTERVIEW_LINK_SENT", "INTERVIEW_SCHEDULED"} else "SENT")).upper()
            if c_status in {"INVALID_PHONE", "SKIPPED", "SKIPPED_INVALID_PHONE"} or status in {"SKIPPED", "INVALID_PHONE", "SKIPPED_INVALID_PHONE"}:
                delivery_status = "INVALID_PHONE"
                skipped_count += 1
            elif c_status == "FAILED":
                delivery_status = "FAILED"
                failed_count += 1
            elif c_status in {"DELIVERED", "READ"} or status in {"INTERESTED", "INTERVIEW_LINK_SENT", "INTERVIEW_SCHEDULED"}:
                delivery_status = "DELIVERED"
                delivered_count += 1
            else:
                delivery_status = "SENT"

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
                    "status": status,
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
            "active_jobs": invites_sent,
            "candidates_screened": invites_sent,
            "strong_matches": interested,
            "whatsapp_outreach": invites_sent,
        },
        "recent_candidates": recent_candidates,
        "pipeline": recent_candidates,
    }


def _clean_whatsapp_phone(raw_phone: str | None) -> str:
    """Normalize and strictly validate an Indian WhatsApp number (must be 10 digits or 12 digits with 91)."""
    if not raw_phone:
        return ""

    clean_phone = "".join(filter(str.isdigit, str(raw_phone)))

    # Strip leading 0 if entered as 0XXXXXXXXXX (11 digits)
    if len(clean_phone) == 11 and clean_phone.startswith("0"):
        clean_phone = clean_phone[1:]

    # If standard 10-digit Indian mobile number, prepend 91
    if len(clean_phone) == 10:
        return "91" + clean_phone

    # If already 12 digits starting with country code 91
    if len(clean_phone) == 12 and clean_phone.startswith("91"):
        return clean_phone

    # Invalid phone length (e.g. 9 digits, 11 digits without 0, etc.)
    return ""


def _whatsapp_headers() -> dict:
    """Build NMVE WhatsApp headers from server-side configuration."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    api_key = getattr(settings, "WHATSAPP_API_KEY", "")
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

    api_key = getattr(
        settings,
        "WHATSAPP_API_KEY",
        "",
    )

    if not api_key:
        print(
            "WHATSAPP_API_KEY is not configured."
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

    request = urllib.request.Request(
        url,
        data=data,
        headers=_whatsapp_headers(),
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


# def _candidate_has_interview_history(
#     db: Session,
#     job_candidate_id: UUID,
# ) -> bool:
#     """Use candidate_assessments to detect an existing interview record."""
#     return db.scalar(
#         select(CandidateAssessment.id)
#         .where(
#             CandidateAssessment.job_candidate_id == job_candidate_id,
#             func.lower(CandidateAssessment.assessment_type).in_(
#                 [
#                     "interview",
#                     "interview_scheduled",
#                     "interview_link",
#                 ]
#             ),
#         )
#         .limit(1)
#     ) is not None


# def get_top_outreach_candidates(
#     db: Session,
#     job_id: UUID,
#     limit: int = 50,
# ) -> list[dict]:
#     """
#     Select the externally ranked top candidates for WhatsApp outreach.

#     The external rank/score is authoritative. NM-HireX only applies the
#     recruitment-history check before sending outreach.
#     """
#     rows = db.execute(
#         select(JobCandidate, Candidate)
#         .join(
#             Candidate,
#             Candidate.id == JobCandidate.candidate_id,
#         )
#         .where(
#             JobCandidate.job_id == job_id,
#             JobCandidate.is_shortlisted.is_(True),
#             JobCandidate.recruitment_status.in_([
#                 "NEW",
#                 "SHORTLISTED",
#             ]),
#         )
#         .order_by(
#             JobCandidate.ranking_position.asc()
#         )
#         .limit(limit)
#     ).all()

#     eligible = []

#     for jc, candidate in rows:
#         has_contact = _candidate_has_contact_history(
#             db,
#             jc.id,
#         )
#         has_interview = _candidate_has_interview_history(
#             db,
#             jc.id,
#         )

#         eligible.append({
#             "job_candidate_id": str(jc.id),
#             "candidate_id": str(candidate.id),
#             "name": candidate.name,
#             "phone": candidate.phone,
#             "email": candidate.email,
#             "rank": jc.ranking_position,
#             "score": (
#                 float(jc.overall_score)
#                 if jc.overall_score is not None
#                 else None
#             ),
#             "has_contact_history": has_contact,
#             "has_interview_history": has_interview,
#             "eligible_for_outreach": not has_contact and not has_interview,
#         })

#     return eligible


def send_top_outreach(
    db: Session,
    job_id: UUID,
    limit: int = 50,
) -> dict:
    """Send WhatsApp only to the top externally ranked candidates with no history."""
    candidates = get_top_outreach_candidates(
        db,
        job_id,
        limit=limit,
    )

    results = []

    for item in candidates:
        if not item["eligible_for_outreach"]:
            results.append({
                **item,
                "status": "SKIPPED_HISTORY",
            })
            continue

        if not item["phone"]:
            results.append({
                **item,
                "status": "SKIPPED_NO_PHONE",
            })
            continue

        sent = _send_whatsapp_to_candidate(
            db=db,
            job_id=job_id,
            candidate_id=UUID(item["candidate_id"]),
        )

        results.append({
            **item,
            "status": "SENT" if sent else "FAILED",
        })

    return {
        "job_id": str(job_id),
        "requested_limit": limit,
        "selected": len(candidates),
        
        "sent": sum(
            1 for item in results
            if item["status"] == "SENT"
        ),
        "skipped_history": sum(
            1 for item in results
            if item["status"] == "SKIPPED_HISTORY"
        ),
        "skipped_no_phone": sum(
            1 for item in results
            if item["status"] == "SKIPPED_NO_PHONE"
        ),
        "failed": sum(
            1 for item in results
            if item["status"] == "FAILED"
        ),
        "results": results,
    }


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
        job_candidate.interview_link = interview_link
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


def update_interview_status(
    db: Session,
    job_candidate_id: UUID,
    status: str,
) -> dict:
    """Update interview status without recalculating candidate score."""
    job_candidate = db.get(JobCandidate, job_candidate_id)
    if not job_candidate:
        raise ValueError("JobCandidate not found")

    normalized = status.strip().upper()
    mapping = {
        "SCHEDULED": "INTERVIEW_SCHEDULED",
        "COMPLETED": "INTERVIEW_COMPLETED",
        "NO_SHOW": "INTERVIEW_NO_SHOW",
        "CANCELLED": "INTERVIEW_CANCELLED",
        "REJECTED": "REJECTED",
    }

    if normalized not in mapping:
        raise ValueError(
            "Invalid interview status. Use SCHEDULED, COMPLETED, NO_SHOW, CANCELLED or REJECTED."
        )

    job_candidate.recruitment_status = mapping[normalized]
    db.commit()

    return {
        "job_candidate_id": str(job_candidate.id),
        "candidate_id": str(job_candidate.candidate_id),
        "status": job_candidate.recruitment_status,
        "interview_scheduled_at": (
            job_candidate.interview_scheduled_at.strftime("%Y-%m-%dT%H:%M:%S")
            if job_candidate.interview_scheduled_at
            else None
        ),
        "interview_link": job_candidate.interview_link,
    }


def mark_candidate_contacted(
    db: Session,
    job_id: UUID,
    candidate_id: UUID,
    target_phone: str | None = None,
):
    return update_candidate_status(
        db,
        job_id,
        candidate_id,
        "CONTACTED",
        target_phone,
    )


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
        c_status = (latest_outbound.status if latest_outbound else ("DELIVERED" if response_text or jc.recruitment_status in {"INTERESTED", "INTERVIEW_LINK_SENT", "INTERVIEW_SCHEDULED"} else "SENT")).upper()
        if c_status == "FAILED":
            delivery_status = "FAILED"
        elif c_status in {"DELIVERED", "READ"} or response_text or jc.recruitment_status in {"INTERESTED", "INTERVIEW_LINK_SENT", "INTERVIEW_SCHEDULED"}:
            delivery_status = "DELIVERED"
        else:
            delivery_status = "SENT"

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
            "status": jc.recruitment_status,
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

def send_naukri_outreach_array(
    db: Session,
    job_id: UUID | None = None,
    candidates: list[dict] | None = None,
    company_name: str | None = None,
    user_id: UUID | None = None,
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
    failed_count = 0
    skipped_count = 0

    for idx, item in enumerate(candidate_list):
        name = str(item.get("name") or "").strip()
        role = str(item.get("role") or (job.title if job else "the position")).strip()
        
        # Phone can be provided as phone, phone_number, mobile, or in the 'no' field
        raw_phone = str(item.get("phone") or item.get("phone_number") or item.get("mobile") or "").strip()
        serial_no = item.get("no", idx + 1)
        if not raw_phone and item.get("no"):
            no_val = str(item.get("no")).strip()
            digits = "".join(filter(str.isdigit, no_val))
            if len(digits) >= 10:
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
            )
            db.add(candidate)
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
            status="SENT",
            sent_at=datetime.utcnow(),
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
        "skipped": skipped_count,
        "failed": failed_count,
        "results": results,
    }
