"""WhatsApp Integration Gateway Service Layer.

This module provides the core service-level orchestration functions connecting the
NM-HireX recruitment platform to the external WhatsApp Integration Gateway (NMVE).

Core Responsibilities:
1. `fetch_schedules`: Retrieves scheduled interview appointments with automatic pagination.
2. `fetch_interview_results`: Retrieves post-interview candidate results and evaluations with auto-pagination.
3. `join_schedules_and_results`: Merges schedule records with interview test results in memory.
4. `fetch_joined_interview_data`: Helper that fetches and merges both schedules and results in a single call.
5. `add_candidate`: Validates candidate data, enforces fixed assessment parameters, strips internal flags,
   calls the external gateway write API, and extracts the candidate's custom `registrationUrl` (test link).
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

# Configure dedicated service logger
logger = logging.getLogger("nmhirex.gateway_service")


# ============================================================
# API 1: FETCH SCHEDULES
# Scope Required: interviews:read
# ============================================================
def fetch_schedules(
    filters: dict[str, Any] | None = None,
    client: WhatsAppGatewayClient | None = None,
    auto_paginate: bool = True,
) -> dict[str, Any]:
    """Retrieve scheduled interviews from the W hatsApp Integration Gateway.

    Detailed Functionality:
    - Queries the endpoint `/api/integrations/whatsapp/raw/schedules` via HTTP POST.
    - Inspects pagination metadata (`totalPages`, `totalCount`, `pageSize`, `page`).
    - If `auto_paginate` is True, iteratively loops through all remaining pages until all
      scheduled candidates across the entire system are assembled into a single continuous list.
    - Safe read call (`is_write=False`): enables automatic 5xx retries in the client.

    Parameters:
        filters (dict[str, Any] | None): Optional search and date criteria. Supported keys:
            - startDate (str): ISO start date filter (e.g. '2026-01-01').
            - endDate (str): ISO end date filter (e.g. '2026-12-31').
            - date (str): Specific calendar date.
            - dateType (str): Field to match date on (e.g. 'interview_date' or 'created_at').
            - is_registered (bool): Filter by candidate registration status.
            - requisition_id (int | str): Filter by specific requisition / job ID.
            - email / candidate_email (str): Candidate email lookup.
            - added_by_email (str): Recruiter or system email filter.
            - search (str): Free-text search term across candidate name and details.
            - pageSize (int): Records per page (default: 50).
            - page (int): Starting page number (default: 1).
        client (WhatsAppGatewayClient | None): Optional custom client instance. Defaults to `default_gateway_client`.
        auto_paginate (bool): If True (default), collects all pages; if False, returns only the first page.

    Returns:
        dict[str, Any]: Standardized response dictionary containing:
            - statusCode (int): HTTP status from gateway (e.g. 200).
            - message (str): Status message (e.g. 'Success').
            - requestId (str | None): Gateway request ID for audit tracing.
            - totalCount (int): Total records matching query across all pages.
            - totalPages (int): Total page count reported by gateway.
            - currentPage (int): Final page index fetched.
            - pageSize (int): Page size used for pagination requests.
            - data (list[dict[str, Any]]): Full array of retrieved schedule objects.

    Raises:
        GatewayAuthError: If Key 2 credentials are invalid or missing.
        GatewayForbiddenError: If Key 2 lacks `interviews:read` scope.
        GatewayRateLimitError: If gateway rate limits are exceeded.
        GatewayServerError: If gateway experiences an internal failure.
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

        # Make read request to gateway schedules endpoint
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

        # Break if pagination is disabled, final page reached, or empty page encountered
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
# Scope Required: interviews:read
# ============================================================
def fetch_interview_results(
    filters: dict[str, Any] | None = None,
    client: WhatsAppGatewayClient | None = None,
    auto_paginate: bool = True,
) -> dict[str, Any]:
    """Retrieve candidate post-interview results and test scores from WhatsApp Gateway.

    Detailed Functionality:
    - Queries the endpoint `/api/integrations/whatsapp/raw/interview-list` via HTTP POST.
    - Retrieves candidate test submissions, test scores, percentage ranks, outcome feedback,
      and completion statuses (e.g. 'Passed', 'Failed', 'Pending').
    - If `auto_paginate` is True, loops through all available result pages to compile a complete list.
    - Safe read call (`is_write=False`): enables automatic 5xx retries.

    Parameters:
        filters (dict[str, Any] | None): Optional search and date criteria. Supported keys:
            - startDate (str): ISO start date filter.
            - endDate (str): ISO end date filter.
            - date (str): Specific date filter.
            - requisition_id (int | str): Filter by specific job requisition.
            - candidate_email (str): Candidate email address.
            - user_id / candidate_id (str): Candidate external ID.
            - added_by_email (str): Recruiter email who invited the candidate.
            - test_type (str): Test type filter (e.g. 'coding', 'aptitude', 'ai_interview').
            - result (str): Outcome filter (e.g. 'Pass', 'Fail', 'Pending').
            - search (str): Search term for candidate name or email.
            - pageSize (int): Page size (default: 50).
            - page (int): Initial page number (default: 1).
        client (WhatsAppGatewayClient | None): Optional custom client instance. Defaults to `default_gateway_client`.
        auto_paginate (bool): If True (default), collects all pages; if False, returns first page.

    Returns:
        dict[str, Any]: Standardized response dictionary containing:
            - statusCode (int): HTTP status from gateway.
            - message (str): Upstream message.
            - requestId (str | None): Request ID for tracing.
            - totalCount (int): Total records matching criteria.
            - totalPages (int): Total pages available upstream.
            - currentPage (int): Final page index fetched.
            - pageSize (int): Page size utilized.
            - data (list[dict[str, Any]]): Full array of candidate interview result records.

    Raises:
        GatewayAuthError: If Key 2 credentials are invalid or missing.
        GatewayForbiddenError: If Key 2 lacks `interviews:read` scope.
        GatewayRateLimitError: If rate limits are exceeded.
        GatewayServerError: If gateway server error occurs.
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

        # Make read request to gateway interview results endpoint
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

        # Break if pagination is disabled, final page reached, or empty page encountered
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
    """Relational join combining interview schedules with interview test results.

    Detailed Functionality:
    - Builds an in-memory index mapping schedules by compound key `f"{schedule_id}_{requisition_id}"`
      and standalone `schedule_id`.
    - Iterates over results, matching each result to its corresponding schedule record.
    - Attaches the complete schedule dictionary inside each result object under the key `"schedule"`.
    - Scans for scheduled interviews that have not yet generated a test result (e.g. upcoming or pending
      interviews) and synthesizes a placeholder result entry with `result="Pending"` and empty score fields.

    Parameters:
        schedules (list[dict[str, Any]]): Array of schedule records from `fetch_schedules()`.
        results (list[dict[str, Any]]): Array of test result records from `fetch_interview_results()`.

    Returns:
        list[dict[str, Any]]: Unified list of merged records containing both schedule and result data.
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

    # Join results with their corresponding schedule record
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

    # Append any schedules that had no interview result recorded yet (pending interviews)
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
    """Fetch both schedules and results from gateway, then merge them into a single report.

    Detailed Functionality:
    - Convenience function that invokes `fetch_schedules()` and `fetch_interview_results()`
      sequentially using the provided filters.
    - Passes both result sets into `join_schedules_and_results()` to form an end-to-end dataset.

    Parameters:
        filters (dict[str, Any] | None): Filter criteria applicable to schedules and results.
        client (WhatsAppGatewayClient | None): Optional client instance.

    Returns:
        dict[str, Any]: Response dictionary with total counts and unified merged records.
    """
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
# Scope Required: candidates:write
# ============================================================
def add_candidate(
    candidate_input: dict[str, Any],
    client: WhatsAppGatewayClient | None = None,
) -> dict[str, Any]:
    """Create a candidate record and schedule their interview via the WhatsApp Gateway.

    Detailed Functionality:
    1. Validation:
       - Ensures `user_name` is present and non-empty.
       - Validates `email` format via standard regex.
       - Normalizes `contact_no`: strips spaces/dashes and verifies it contains 10-15 digits with country code.
       - Validates `interview_date` in strict `YYYY-MM-DD` format.
       - Validates `interview_time` in strict `HH:mm` 24-hour format (e.g. '14:30').
    2. Workflow Isolation:
       - Strictly strips the `automate` key (`candidate_input.pop("automate", None)`) to ensure internal
         NM-HireX automation routing flags are never leaked to the external gateway.
    3. Gateway Specification Enforcement:
       - Injects fixed mandatory assessment criteria required by the gateway engine:
         `technical_round: 1`, `one2one_round: 1`, `comm_skill_rating: 4`, `cultural_fit_rating: 4`,
         and `operation: "addcandidate"`.
       - Resolves `requisition_id` and `request_id` (fallback: `settings.NMHIREX_DEFAULT_REQUISITION_ID`, 506).
    4. Execution & URL Extraction:
       - Dispatches request via `POST /api/integrations/whatsapp/raw/add-candidate` with `is_write=True`.
       - Extracts and normalizes the generated test URL (`registrationUrl` / `testUrl`).
       - This `registrationUrl` is used as the candidate's online interview test link.

    Parameters:
        candidate_input (dict[str, Any]): Dictionary of candidate information. Required keys:
            - user_name / name (str): Full candidate name.
            - email (str): Valid email address.
            - contact_no / phone / no (str): Phone number with country code (10-15 digits).
            - current_company / company (str): Current employer name.
            - interview_date (str): 'YYYY-MM-DD'.
            - interview_time (str): 'HH:mm' in 24-hour time.
            Optional keys: `experience`, `job_role`, `request_id`, `requisition_id`, `resume_url`, etc.
        client (WhatsAppGatewayClient | None): Optional custom client instance.

    Returns:
        dict[str, Any]: Gateway API response dictionary containing `registrationUrl`.

    Raises:
        GatewayValidationError: If any required parameter is missing or violates formatting constraints.
        GatewayAuthError: If Key 2 credentials are invalid or missing.
        GatewayForbiddenError: If Key 2 lacks `candidates:write` scope.
        GatewayServerError: If gateway fails during candidate registration.
    """
    gw = client or default_gateway_client

    if not isinstance(candidate_input, dict):
        raise GatewayValidationError("Candidate input must be a valid JSON dictionary.")

    # Strictly strip 'automate' flag so it never enters the addcandidate API payload
    candidate_input.pop("automate", None)

    # 1. Validate User Name
    user_name = str(
        candidate_input.get("user_name")
        or candidate_input.get("name")
        or ""
    ).strip()
    if not user_name:
        raise GatewayValidationError("user_name is required.")

    # 2. Validate Email
    email = str(candidate_input.get("email") or "").strip()
    if not email or not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        raise GatewayValidationError(f"A valid email is required (received: '{email}').")

    # 3. Validate Contact Number: digits only, 10 to 15 digits with country code
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

    # 5. Validate Interview Date (YYYY-MM-DD)
    interview_date = str(candidate_input.get("interview_date") or "").strip()
    try:
        datetime.strptime(interview_date, "%Y-%m-%d")
    except ValueError:
        raise GatewayValidationError(
            f"Invalid interview_date '{interview_date}': must be in YYYY-MM-DD format."
        )

    # 6. Validate Interview Time (HH:mm)
    interview_time = str(candidate_input.get("interview_time") or "").strip()
    try:
        datetime.strptime(interview_time, "%H:%M")
    except ValueError:
        raise GatewayValidationError(
            f"Invalid interview_time '{interview_time}': must be in HH:mm 24-hour format (e.g. '11:00')."
        )

    # 7. Request ID & Requisition ID resolution
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
            requisition_id_val = parsed_id if parsed_id > 0 else req_str
        except (ValueError, TypeError):
            requisition_id_val = req_str

    if requisition_id_val is None:
        requisition_id_val = int(getattr(settings, "NMHIREX_DEFAULT_REQUISITION_ID", 506))

    # 8. Build full payload adhering strictly to gateway specifications
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
        "technical_round": 1,         # Fixed gateway requirement
        "one2one_round": 1,           # Fixed gateway requirement
        "cultural_fit": str(candidate_input.get("cultural_fit") or ""),
        "request_id": request_id_val,
        "requisition_id": requisition_id_val,
        "comm_skill_rating": 4,       # Fixed gateway requirement
        "cultural_fit_rating": 4,     # Fixed gateway requirement
        "operation": "addcandidate",  # Fixed gateway requirement
    }

    logger.info(
        "Calling WhatsApp Gateway add-candidate for '%s' (%s, %s) with requisition %s",
        payload["user_name"],
        payload["email"],
        payload["contact_no"],
        payload["requisition_id"],
    )

    # Execute request with is_write=True (disables 5xx auto-retries to prevent duplicate mutations)
    res = gw.post(
        "/api/integrations/whatsapp/raw/add-candidate",
        payload=payload,
        is_write=True,
    )

    # Capture and standardize registrationUrl / testUrl from various possible response shapes
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

