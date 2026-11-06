"""WhatsApp Integration Gateway Service Layer.

Provides the 3 core gateway integration functions:
1. fetch_schedules (fetchSchedules): loops through all pages to retrieve all scheduled interviews
2. fetch_interview_results (fetchInterviewResults): loops through all pages for interview results
3. add_candidate (addCandidate): builds exact candidate payload with fixed ratings/rounds and calls write API
4. join_schedules_and_results: joins interview results and schedule records by schedule_id and requisition_id
"""

import logging
import re
from datetime import datetime
from typing import Any

from .config import settings
from .gateway_client import (
    GatewayValidationError,
    WhatsAppGatewayClient,
    default_gateway_client,
)

logger = logging.getLogger("nmhirex.gateway_service")


# ============================================================
# API 1: FETCH SCHEDULES
# Scope: interviews:read
# ============================================================
def fetch_schedules(
    filters: dict[str, Any] | None = None,
    client: WhatsAppGatewayClient | None = None,
    auto_paginate: bool = True,
) -> dict[str, Any]:
    """List scheduled interviews from WhatsApp Gateway.

    Loops through all pages using `totalPages` to assemble a complete dataset.

    Args:
        filters: Optional filter dictionary (startDate, endDate, date, dateType,
                 is_registered, requisition_id, email/candidate_email, added_by_email, search, all, etc.)
        client: Optional custom WhatsAppGatewayClient instance
        auto_paginate: Whether to loop through all pages (default True)

    Returns:
        dict: { "statusCode": 200, "totalCount": int, "totalPages": int, "data": [...] }
    """
    gw = client or default_gateway_client
    base_payload = dict(filters or {})
    page_size = base_payload.get("pageSize", 50)
    current_page = base_payload.get("page", 1)

    all_data: list[dict[str, Any]] = []
    total_count = 0
    total_pages = 1
    last_status = 200
    last_message = "Success"
    last_request_id = None

    while True:
        payload = {
            **base_payload,
            "page": current_page,
            "pageSize": page_size,
        }

        res = gw.post(
            "/api/integrations/whatsapp/raw/schedules",
            payload=payload,
            is_write=False,
        )

        last_status = res.get("statusCode", 200)
        last_message = res.get("message", "Success")
        last_request_id = res.get("requestId")

        page_data = res.get("data") or []
        all_data.extend(page_data)

        total_count = res.get("totalCount", len(all_data))
        total_pages = res.get("totalPages", 1)

        logger.info(
            "fetch_schedules: page %d of %d fetched (%d items, total %d)",
            current_page,
            total_pages,
            len(page_data),
            total_count,
        )

        if not auto_paginate or current_page >= total_pages or not page_data:
            break

        current_page += 1

    return {
        "statusCode": last_status,
        "message": last_message,
        "requestId": last_request_id,
        "totalCount": total_count,
        "totalPages": total_pages,
        "currentPage": current_page,
        "pageSize": page_size,
        "data": all_data,
    }


# ============================================================
# API 2: FETCH INTERVIEW RESULTS
# Scope: interviews:read
# ============================================================
def fetch_interview_results(
    filters: dict[str, Any] | None = None,
    client: WhatsAppGatewayClient | None = None,
    auto_paginate: bool = True,
) -> dict[str, Any]:
    """Retrieve post-interview results from WhatsApp Gateway.

    Loops through all pages using `totalPages` to assemble a complete dataset.

    Args:
        filters: Optional filter dictionary (startDate, endDate, date,
                 requisition_id, candidate_email, user_id/candidate_id,
                 added_by_email, test_type, result, search, all)
        client: Optional custom WhatsAppGatewayClient instance
        auto_paginate: Whether to loop through all pages (default True)

    Returns:
        dict: { "statusCode": 200, "totalCount": int, "totalPages": int, "data": [...] }
    """
    gw = client or default_gateway_client
    base_payload = dict(filters or {})
    page_size = base_payload.get("pageSize", 50)
    current_page = base_payload.get("page", 1)

    all_data: list[dict[str, Any]] = []
    total_count = 0
    total_pages = 1
    last_status = 200
    last_message = "Success"
    last_request_id = None

    while True:
        payload = {
            **base_payload,
            "page": current_page,
            "pageSize": page_size,
        }

        res = gw.post(
            "/api/integrations/whatsapp/raw/interview-list",
            payload=payload,
            is_write=False,
        )

        last_status = res.get("statusCode", 200)
        last_message = res.get("message", "Success")
        last_request_id = res.get("requestId")

        page_data = res.get("data") or []
        all_data.extend(page_data)

        total_count = res.get("totalCount", len(all_data))
        total_pages = res.get("totalPages", 1)

        logger.info(
            "fetch_interview_results: page %d of %d fetched (%d items, total %d)",
            current_page,
            total_pages,
            len(page_data),
            total_count,
        )

        if not auto_paginate or current_page >= total_pages or not page_data:
            break

        current_page += 1

    return {
        "statusCode": last_status,
        "message": last_message,
        "requestId": last_request_id,
        "totalCount": total_count,
        "totalPages": total_pages,
        "currentPage": current_page,
        "pageSize": page_size,
        "data": all_data,
    }


# ============================================================
# HELPER: JOIN SCHEDULES AND RESULTS
# ============================================================
def join_schedules_and_results(
    schedules: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Joins interview results with schedules.

    Matching criteria: interview_schedule_id (results) == schedule_id (schedules)
    and requisition_id.
    """
    schedule_map: dict[str, dict[str, Any]] = {}
    for s in schedules:
        sched_id = str(s.get("schedule_id") or "")
        req_id = str(s.get("requisition_id") or "")
        if sched_id:
            schedule_map[f"{sched_id}_{req_id}"] = s
            schedule_map[sched_id] = s

    joined: list[dict[str, Any]] = []
    matched_schedule_ids = set()

    for r in results:
        sched_id = str(r.get("interview_schedule_id") or "")
        req_id = str(r.get("requisition_id") or "")
        key = f"{sched_id}_{req_id}"
        matching_schedule = schedule_map.get(key) or schedule_map.get(sched_id)

        if matching_schedule:
            matched_schedule_ids.add(sched_id)

        item = {
            **r,
            "schedule": matching_schedule or {},
        }
        joined.append(item)

    # Append any schedules that had no interview result recorded yet
    for s in schedules:
        sched_id = str(s.get("schedule_id") or "")
        if sched_id and sched_id not in matched_schedule_ids:
            joined.append({
                "interview_id": None,
                "candidate_id": s.get("schedule_id"),
                "candidate_name": s.get("user_name"),
                "candidate_email": s.get("email"),
                "candidate_number": s.get("contact_no"),
                "test_type": None,
                "test_type_name": None,
                "result": "Pending",
                "score": None,
                "score_percentage": None,
                "feedback": None,
                "requisition_id": s.get("requisition_id"),
                "interview_schedule_id": s.get("schedule_id"),
                "requisitionDetails": s.get("requisitionDetails"),
                "schedule": s,
            })

    return joined


def fetch_joined_interview_data(
    filters: dict[str, Any] | None = None,
    client: WhatsAppGatewayClient | None = None,
) -> dict[str, Any]:
    """Fetches schedules and results, then merges them."""
    schedules_res = fetch_schedules(filters, client=client)
    results_res = fetch_interview_results(filters, client=client)

    joined_list = join_schedules_and_results(
        schedules_res.get("data", []),
        results_res.get("data", []),
    )

    return {
        "statusCode": 200,
        "totalCount": len(joined_list),
        "schedulesCount": schedules_res.get("totalCount", 0),
        "resultsCount": results_res.get("totalCount", 0),
        "data": joined_list,
    }


# ============================================================
# API 3: ADD CANDIDATE & SCHEDULE INTERVIEW
# Scope: candidates:write
# ============================================================
def add_candidate(
    candidate_input: dict[str, Any],
    client: WhatsAppGatewayClient | None = None,
) -> dict[str, Any]:
    """Create a candidate and schedule the interview via WhatsApp Gateway.

    Payload format:
    - user_name: candidate full name
    - email: candidate email
    - contact_no: digits only with country code (10 to 15 digits)
    - current_company: candidate current company
    - interview_date: YYYY-MM-DD
    - interview_time: HH:mm
    - technical_round: 1 (fixed)
    - one2one_round: 1 (fixed)
    - comm_skill_rating: 4 (fixed)
    - cultural_fit_rating: 4 (fixed)
    - operation: "addcandidate" (fixed)
    - requisition_id / request_id: from database or fallback default
    - other fields: empty string ""

    Returns:
        dict: Gateway response including `registrationUrl`.
    """
    gw = client or default_gateway_client

    if not isinstance(candidate_input, dict):
        raise GatewayValidationError("Candidate input must be a valid JSON dictionary.")

    # Strictly strip 'automate' flag so it never enters the addcandidate API payload
    candidate_input.pop("automate", None)

    # 1. User Name
    user_name = str(
        candidate_input.get("user_name")
        or candidate_input.get("name")
        or ""
    ).strip()
    if not user_name:
        raise GatewayValidationError("user_name is required.")

    # 2. Email
    email = str(candidate_input.get("email") or "").strip()
    if not email or not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        raise GatewayValidationError(f"A valid email is required (received: '{email}').")

    # 3. Contact Number: digits only, 10 to 15 digits
    raw_contact = str(
        candidate_input.get("contact_no")
        or candidate_input.get("phone")
        or candidate_input.get("no")
        or candidate_input.get("phone_number")
        or ""
    ).strip()
    digits_contact = re.sub(r"\D", "", raw_contact)
    if not (10 <= len(digits_contact) <= 15):
        raise GatewayValidationError(
            f"Invalid contact_no '{raw_contact}': must contain between 10 and 15 digits with country code."
        )

    # 4. Current Company
    current_company = str(
        candidate_input.get("current_company")
        or candidate_input.get("company")
        or ""
    ).strip()

    # 5. Interview Date (YYYY-MM-DD)
    interview_date = str(candidate_input.get("interview_date") or "").strip()
    try:
        datetime.strptime(interview_date, "%Y-%m-%d")
    except ValueError:
        raise GatewayValidationError(
            f"Invalid interview_date '{interview_date}': must be in YYYY-MM-DD format."
        )

    # 6. Interview Time (HH:mm)
    interview_time = str(candidate_input.get("interview_time") or "").strip()
    try:
        datetime.strptime(interview_time, "%H:%M")
    except ValueError:
        raise GatewayValidationError(
            f"Invalid interview_time '{interview_time}': must be in HH:mm 24-hour format (e.g. '11:00')."
        )

    # 7. Request ID & Requisition ID
    req_id_input = candidate_input.get("request_id")
    if req_id_input is not None and str(req_id_input).strip():
        req_str = str(req_id_input).strip()
        try:
            request_id_val = int(req_str)
        except (ValueError, TypeError):
            request_id_val = req_str
    else:
        request_id_val = getattr(settings, "NMHIREX_DEFAULT_REQUISITION_ID", 506)

    requisition_id_input = candidate_input.get("requisition_id")
    requisition_id_val = None
    if requisition_id_input is not None and str(requisition_id_input).strip():
        req_str = str(requisition_id_input).strip()
        try:
            parsed_id = int(req_str)
            if parsed_id > 0:
                requisition_id_val = parsed_id
        except (ValueError, TypeError):
            requisition_id_val = None

    if requisition_id_val is None:
        requisition_id_val = int(getattr(settings, "NMHIREX_DEFAULT_REQUISITION_ID", 506))

    # 8. Build full payload adhering strictly to the user specification
    payload: dict[str, Any] = {
        "user_name": user_name,
        "email": email,
        "contact_no": digits_contact,
        "current_company": current_company,
        "interview_date": interview_date,
        "interview_time": interview_time,
        "other_details": str(candidate_input.get("other_details") or ""),
        "resume_url": str(candidate_input.get("resume_url") or ""),
        "added_by_email": str(candidate_input.get("added_by_email") or "sheela@virtualemployee.com"),
        "added_by_name": str(candidate_input.get("added_by_name") or "Sheela AI"),
        "job_status": str(candidate_input.get("job_status") or ""),
        "notice_period": str(candidate_input.get("notice_period") or ""),
        "current_ctc": str(candidate_input.get("current_ctc") or ""),
        "expected_ctc": str(candidate_input.get("expected_ctc") or ""),
        "experience": str(candidate_input.get("experience") or ""),
        "source_of_candidate": str(candidate_input.get("source_of_candidate") or ""),
        "is_notice_buyout": str(candidate_input.get("is_notice_buyout") or ""),
        "job_role": str(candidate_input.get("job_role") or candidate_input.get("role") or ""),
        "reason_job_change": str(candidate_input.get("reason_job_change") or ""),
        "salaryNegotiation": str(candidate_input.get("salaryNegotiation") or ""),
        "candidate_ques": str(candidate_input.get("candidate_ques") or ""),
        "interview_medium": str(candidate_input.get("interview_medium") or "NM Interview"),
        "technical_round": 1,         # Fixed
        "one2one_round": 1,           # Fixed
        "cultural_fit": str(candidate_input.get("cultural_fit") or ""),
        "request_id": request_id_val,
        "requisition_id": requisition_id_val,
        "comm_skill_rating": 4,       # Fixed
        "cultural_fit_rating": 4,     # Fixed
        "operation": "addcandidate",  # Fixed
    }

    logger.info(
        "Calling WhatsApp Gateway add-candidate for '%s' (%s, %s) with requisition %s",
        payload["user_name"],
        payload["email"],
        payload["contact_no"],
        payload["requisition_id"],
    )

    # Execute request with is_write=True (disables 5xx auto-retries)
    res = gw.post(
        "/api/integrations/whatsapp/raw/add-candidate",
        payload=payload,
        is_write=True,
    )

    # Capture registrationUrl / testUrl
    reg_url = (
        res.get("registrationUrl")
        or res.get("registration_url")
        or res.get("testUrl")
        or res.get("test_url")
        or (res.get("data") if isinstance(res.get("data"), dict) else {}).get("registrationUrl")
        or (res.get("data") if isinstance(res.get("data"), dict) else {}).get("registration_url")
        or (res.get("data") if isinstance(res.get("data"), dict) else {}).get("testUrl")
        or (res.get("result") if isinstance(res.get("result"), dict) else {}).get("registrationUrl")
    )
    if reg_url:
        res["registrationUrl"] = reg_url

    return res


# Backward-compatible camelCase aliases
fetchSchedules = fetch_schedules
fetchInterviewResults = fetch_interview_results
addCandidate = add_candidate

