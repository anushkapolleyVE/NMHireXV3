import re
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .config import settings


# =========================================================
# REQUEST SCHEMAS
# =========================================================

class JobCreateRequest(BaseModel):

    title: str

    vereq_number: str | None = None

    description: str | None = None


class MatchedCandidateRequest(BaseModel):

    external_candidate_id: str | None = None

    name: str = "Unknown Candidate"

    email: str | None = None

    phone: str | None = None

    location: str | None = None

    resume_url: str | None = None

    # Normalized score
    match_score: float | None = None

    # Alternative names in case the external API uses them
    score: float | None = None

    sheela_score: float | None = None

    ranking_position: int | None = None

    rank: int | None = None

    raw_data: dict[str, Any] = Field(
        default_factory=dict
    )


class MatchedCandidatesBatchRequest(BaseModel):

    vereq_number: str | None = None

    candidates: list[MatchedCandidateRequest]

    top_n: int = Field(
        default=100,
        ge=1,
        le=1000
    )


class OutreachRequest(BaseModel):

    limit: int = Field(
        default=50,
        ge=1,
        le=100
    )


class ScheduleInterviewRequest(BaseModel):

    scheduled_at: datetime

    duration_minutes: int = Field(
        default=30,
        ge=15,
        le=180
    )

    meeting_link: str | None = None


class InterviewStatusRequest(BaseModel):

    status: str


# =========================================================
# PHONE
# =========================================================

def normalize_phone(phone: str | None) -> str | None:

    if not phone:
        return None

    digits = re.sub(r"\D", "", phone)

    if len(digits) == 10:
        digits = settings.DEFAULT_COUNTRY_CODE + digits

    return digits


# =========================================================
# WHATSAPP HTTP CLIENT
# =========================================================

def _whatsapp_headers():

    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.WHATSAPP_API_KEY}",
        "api-key": settings.WHATSAPP_API_KEY,
    }


def _send_whatsapp(payload: dict):

    if settings.WHATSAPP_MOCK:

        return {
            "success": True,
            "mock": True,
            "message_id": "mock-message-id"
        }

    if not settings.WHATSAPP_API_KEY:

        raise RuntimeError(
            "WHATSAPP_API_KEY is not configured"
        )

    response = httpx.post(
        settings.WHATSAPP_BASE_URL,
        headers=_whatsapp_headers(),
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    try:
        return response.json()
    except Exception:
        return {
            "success": True,
            "raw": response.text
        }


# =========================================================
# SEND INITIAL WHATSAPP TEMPLATE
# =========================================================

def send_whatsapp_template(
    phone: str,
    reference_id: str
):

    phone = normalize_phone(phone)

    if not phone:
        raise ValueError("Candidate phone number is missing")

    payload = {
        "to": phone,
        "type": "template",
        "template": {
            "name": settings.WHATSAPP_TEMPLATE_NAME,
            "language": {
                "code": settings.WHATSAPP_TEMPLATE_LANGUAGE
            }
        },
        "referenceId": reference_id,
        "callbackUrl": settings.WHATSAPP_CALLBACK_URL
    }

    return _send_whatsapp(payload)


# =========================================================
# SEND TEXT
# =========================================================

def send_whatsapp_text(
    phone: str,
    message: str,
    reference_id: str | None = None
):

    phone = normalize_phone(phone)

    if not phone:
        raise ValueError("Candidate phone number is missing")

    payload = {
        "to": phone,
        "type": "text",
        "text": {
            "body": message
        }
    }

    if reference_id:
        payload["referenceId"] = reference_id

    return _send_whatsapp(payload)


# =========================================================
# SCHEDULING LINK
# =========================================================

def build_schedule_url(job_candidate_id: str):

    return (
        f"{settings.FRONTEND_URL.rstrip('/')}"
        f"/schedule/{job_candidate_id}"
    )


# =========================================================
# RESPONSE CLASSIFICATION
# =========================================================

def classify_candidate_response(
    message: str
) -> str:

    text = message.lower().strip()

    # Check negative FIRST
    negative_patterns = [
        r"\bno\b",
        r"\bno thanks\b",
        r"\bnot interested\b",
        r"\bdo not want\b",
        r"\bdon't want\b",
        r"\bdecline\b",
        r"\bnot looking\b",
    ]

    for pattern in negative_patterns:

        if re.search(pattern, text):

            return "NOT_INTERESTED"

    positive_patterns = [
        r"\byes\b",
        r"\binterested\b",
        r"\bsure\b",
        r"\bok\b",
        r"\bokay\b",
        r"\binterview\b",
        r"\bproceed\b",
        r"\bschedule\b",
    ]

    for pattern in positive_patterns:

        if re.search(pattern, text):

            return "INTERESTED"

    return "UNKNOWN"


# =========================================================
# WEBHOOK PARSING
# =========================================================

def _find_value(
    data: Any,
    keys: list[str]
):

    if isinstance(data, dict):

        for key in keys:

            if key in data and data[key]:

                value = data[key]

                if isinstance(value, (str, int, float)):

                    return str(value)

        for value in data.values():

            result = _find_value(value, keys)

            if result:

                return result

    elif isinstance(data, list):

        for value in data:

            result = _find_value(value, keys)

            if result:

                return result

    return None


def extract_webhook_event(
    payload: dict
):

    phone = _find_value(
        payload,
        [
            "from",
            "phone",
            "sender",
            "wa_id",
            "waId",
            "phoneNumber",
            "fromNumber"
        ]
    )

    text = _find_value(
        payload,
        [
            "text",
            "body",
            "message",
            "messageText",
            "content"
        ]
    )

    reference_id = _find_value(
        payload,
        [
            "referenceId",
            "reference_id"
        ]
    )

    provider_message_id = _find_value(
        payload,
        [
            "messageId",
            "message_id",
            "id"
        ]
    )

    return {
        "phone": normalize_phone(phone),
        "text": text or "",
        "reference_id": reference_id,
        "provider_message_id": provider_message_id,
        "raw_payload": payload
    }