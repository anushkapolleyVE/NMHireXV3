# NM-HireX Recruitment Platform

NM-HireX is an AI-powered recruitment OS that integrates candidate sourcing, automated outreach, WhatsApp interview scheduling, and scoring.

---

## WhatsApp Integration Gateway

NM-HireX integrates 3 core endpoints from the external **WhatsApp Integration Gateway**:
1. **Schedules API** (Read-only, scope `interviews:read`)
2. **Interview Results API** (Read-only, scope `interviews:read`)
3. **Add Candidate & Schedule API** (Write, scope `candidates:write`)

The WhatsApp automated messaging (candidate outreach, intent recognition, and date/time selection links) runs directly on the gateway. NM-HireX integrates with the gateway via a resilient, typed client and server-side service layer.

---

### Environment Setup (Dual API Key Architecture)

Add the following variables to your `backend/.env` file:

```env
# -------------------------------------------------------------
# KEY 1: WHATSAPP MESSAGING (PERMISSION: SEND MESSAGES ONLY)
# -------------------------------------------------------------
WHATSAPP_MESSAGE_API_KEY=wa_live_<messagingKeyId>_<secret>
WHATSAPP_API_KEY=wa_live_<messagingKeyId>_<secret>

# -------------------------------------------------------------
# KEY 2: WHATSAPP INTEGRATION GATEWAY (PERMISSION: /addcandidates TEST URL GENERATION)
# -------------------------------------------------------------
NMHIREX_GATEWAY_URL=https://nmve.io/whatsapp
NMHIREX_GATEWAY_API_KEY=wa_live_<gatewayKeyId>_<secret>
NMHIREX_API_KEY=wa_live_<gatewayKeyId>_<secret>
NMHIREX_GATEWAY_TIMEOUT_SECONDS=25
NMHIREX_DEFAULT_REQUISITION_ID=506
```

> **Security Note:** Both API keys are stored and used **server-side only**. They are never exposed in frontend code, browser network bundles, or server logs. Key 1 is strictly isolated for outbound messaging, and Key 2 is strictly isolated for `/addcandidates` URL generation and gateway read queries.

---

### The 3 Gateway APIs

#### 1. Schedules (`POST /api/integrations/whatsapp/raw/schedules`)
- **Scope:** `interviews:read`
- **Purpose:** Fetches all scheduled interviews, candidate registration status, interview rounds, and next steps.
- **Filters:** `page`, `pageSize`, `date`, `startDate`, `endDate`, `dateType` ("interview_date"), `is_registered`, `requisition_id`, `candidate_email`/`email`, `search`, `all`.
- **Pagination:** Automatically loops through all pages using `totalPages` to consolidate records.
- **Project Endpoints:**
  - `POST /api/gateway/schedules`
  - `GET /api/gateway/schedules?startDate=2026-11-01&endDate=2026-11-05`

#### 2. Interview Results (`POST /api/integrations/whatsapp/raw/interview-list`)
- **Scope:** `interviews:read`
- **Purpose:** Fetches post-interview results, test type, score, pass/fail result, and examiner feedback.
- **Filters:** `page`, `pageSize`, `startDate`, `endDate`, `date`, `requisition_id`, `candidate_email`, `user_id`, `test_type`, `result`, `search`, `all`.
- **Join Key:** Joins with schedules on `interview_schedule_id == schedule_id` and `requisition_id`.
- **Project Endpoints:**
  - `POST /api/gateway/interview-results`
  - `GET /api/gateway/interview-results`
  - `GET /api/gateway/interviews-joined` (merged report)

#### 3. Add Candidate & Schedule (`POST /api/integrations/whatsapp/raw/add-candidate`)
- **Scope:** `candidates:write`
- **Purpose:** Creates the candidate in the gateway, schedules the interview in one transaction, and triggers automated WhatsApp outreach.
- **Project Endpoints:**
  - `POST /api/gateway/add-candidate`
  - `POST /api/gateway/candidates`
- **Payload Schema:**
```json
{
  "user_name": "Sayank",
  "email": "sayank@gmail.com",
  "contact_no": "918506002804",
  "current_company": "ABCD Technologies Pvt. Ltd",
  "interview_date": "2026-11-22",
  "interview_time": "11:00",
  "other_details": "",
  "resume_url": "",
  "added_by_email": "sheela@virtualemployee.com",
  "added_by_name": "Sheela AI",
  "job_status": "",
  "notice_period": "",
  "current_ctc": "",
  "expected_ctc": "",
  "experience": "",
  "source_of_candidate": "",
  "is_notice_buyout": "",
  "job_role": "Software Engineer",
  "reason_job_change": "",
  "salaryNegotiation": "",
  "candidate_ques": "",
  "interview_medium": "NM Interview",
  "technical_round": 1,
  "one2one_round": 1,
  "cultural_fit": "",
  "request_id": 506,
  "requisition_id": 506,
  "comm_skill_rating": 4,
  "cultural_fit_rating": 4,
  "operation": "addcandidate"
}
```
- **Rules & Defaults:**
  - `technical_round`: 1 (fixed)
  - `one2one_round`: 1 (fixed)
  - `comm_skill_rating`: 4 (fixed)
  - `cultural_fit_rating`: 4 (fixed)
  - `operation`: "addcandidate" (fixed)
  - Unused optional fields default to `""`
  - **No 5xx Auto-Retry:** Write operations are strictly prevented from auto-retrying on 5xx errors to prevent duplicate candidates or double scheduling.
  - **Meeting Link Replacement:** The response returns `registrationUrl`, which is stored in `job_candidate.interview_link` and sent to the candidate instead of Microsoft Teams.

---

### Outreach & Candidate Sourcing (`/api/outreach/send-array`)

The candidate batch ingestion accepts:
- `user_name` (or `name`)
- `email`
- `contact_no` / `phone`
- `job_role` (or `role`)
- `current_company`

When a candidate confirms their slot via `/api/scheduling/confirm`, the system automatically fetches their details, calls the gateway's `/add-candidate`, and replaces the Teams meeting link with the returned `registrationUrl`.

---

### Error Handling & Request Tracing

| Status Code | Typed Exception | Description & Gateway Behavior |
|-------------|-----------------|--------------------------------|
| **401** | `GatewayAuthError` | Invalid, expired, or revoked API key. Check `NMHIREX_API_KEY`. |
| **403** | `GatewayForbiddenError` | Missing required scope (`interviews:read` or `candidates:write`) or IP not allowed. |
| **422** | `GatewayValidationError` | Validation error. Detailed message extracted and displayed. |
| **429** | `GatewayRateLimitError` | Rate limited. Client automatically inspects `Retry-After` header and retries up to 3 times before failing. |
| **5xx / 503** | `GatewayServerError` | Upstream server error. **Read** calls retry up to 2 times with exponential backoff. **Write** calls fail immediately without blind retry. |

Every request logs `requestId` (from header `x-request-id` or JSON payload) for end-to-end tracing.

---

### Testing the Integration

Run the standalone read test script from the `backend/` directory:

```bash
cd backend
python test_gateway_reads.py
```

This script queries `fetch_schedules` and `fetch_interview_results` for the date range `2026-11-01` to `2026-11-05` and prints `totalCount`, page counts, and `requestId`.

