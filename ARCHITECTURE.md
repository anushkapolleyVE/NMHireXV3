# NM-HireX — Architecture & Developer Guide

> **Purpose:** A complete reference for new team members to understand the system without asking questions.  
> Last updated: November 2026

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Repository Layout](#3-repository-layout)
4. [Architecture Diagram](#4-architecture-diagram)
5. [Dual API Key Architecture (CRITICAL)](#5-dual-api-key-architecture-critical)
6. [Candidate Recruitment Flow](#6-candidate-recruitment-flow)
7. [Database Schema](#7-database-schema)
8. [Backend API Reference](#8-backend-api-reference)
9. [Frontend Routes & Pages](#9-frontend-routes--pages)
10. [Environment Variables](#10-environment-variables)
11. [Running Locally](#11-running-locally)
12. [Deployment (Render)](#12-deployment-render)
13. [Key Constraints & Gotchas](#13-key-constraints--gotchas)
14. [Known Error Patterns & Fixes](#14-known-error-patterns--fixes)

---

## 1. Project Overview

**NM-HireX** is a recruiter outreach automation platform. Recruiters paste in a list of shortlisted candidates and the system:

1. Sends WhatsApp outreach messages to each candidate.
2. Receives replies via webhook.
3. Detects candidate intent (Interested / Not Interested).
4. Sends a self-scheduling link to interested candidates.
5. Candidate picks a date/time slot → system books the interview.
6. Calls an external WhatsApp Integration Gateway (`nmve.io`) to generate a TeckValley interview registration URL.
7. Sends a WhatsApp confirmation with the interview link.

There is also a **manual outreach mode** (`automate: "no"`) where candidates are queued for recruiter review before any WhatsApp message is sent.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy (async ORM), Pydantic v2 |
| **Database** | PostgreSQL (hosted on Render) |
| **Frontend** | React 18 (Vite), Tailwind CSS, React Router v6 |
| **Auth** | JWT (python-jose), bcrypt password hashing |
| **WhatsApp** | nmve.io — two separate API keys (see §5) |
| **Deployment** | Render (backend + DB) — auto-deploys on push to `main` |
| **Scheduling** | APScheduler (`backend/app/scheduler.py`) — reminder messages |

---

## 3. Repository Layout

```
NMHireXV3/
├── backend/
│   ├── app/
│   │   ├── api.py              # All FastAPI route handlers
│   │   ├── auth.py             # JWT creation/verification, password hashing
│   │   ├── config.py           # Pydantic Settings (reads .env)
│   │   ├── database.py         # SQLAlchemy engine, session factory
│   │   ├── gateway_client.py   # Low-level HTTP client for nmve.io Gateway
│   │   ├── gateway_service.py  # Business logic wrapping gateway_client
│   │   ├── main.py             # FastAPI app factory, CORS, router mount
│   │   ├── models.py           # SQLAlchemy ORM models (5 active tables)
│   │   ├── scheduler.py        # APScheduler: 24h & 1h interview reminders
│   │   └── tools_function.py   # Core business logic (outreach, webhook, scheduling)
│   ├── .env                    # Local secrets (never committed)
│   ├── .env.example            # Template — safe to commit
│   ├── init_db.py              # One-time DB table creation script
│   ├── Procfile                # Render start command
│   ├── requirements.txt        # Python dependencies
│   ├── test_dual_key_flow.py   # Key isolation tests (run before push)
│   └── test_gateway_reads.py   # Gateway read-only endpoint tests
├── frontend/
│   ├── src/
│   │   ├── pages/              # One file per route (see §9)
│   │   ├── components/
│   │   │   └── Header.jsx      # Nav bar with auth-aware links
│   │   └── utils/
│   │       └── api.js          # All fetch() wrappers — single source of truth
│   ├── .env                    # VITE_API_BASE_URL
│   ├── .env.example            # Template
│   ├── package.json
│   └── vite.config.js
├── render.yaml                 # Render IaC definition (backend service + DB)
├── ARCHITECTURE.md             # This file
└── README.md
```

---

## 4. Architecture Diagram

```
Recruiter Browser
      │
      │  HTTPS
      ▼
┌─────────────────────┐
│   React Frontend    │  Vite · Tailwind · React Router
│  (Render Static /   │
│   Vercel / local)   │
└──────────┬──────────┘
           │  REST (JWT Bearer)
           ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend (Render Web Service)        │
│  api.py ──► tools_function.py ──► models.py             │
│                │                                         │
│          scheduler.py (APScheduler reminders)            │
│                │                                         │
│       gateway_service.py                                │
│          │           │                                   │
│    Key 1 (send)   Key 2 (addcandidates)                 │
└──────┬───┴───────────┴──────────────────────────────────┘
       │               │
       │               │  HTTPS POST /api/integrations/whatsapp/raw/add-candidate
       │               ▼
       │        ┌──────────────────┐
       │        │   nmve.io        │
       │        │  Gateway API     │  Returns registrationUrl
       │        └──────────────────┘
       │
       │  HTTPS POST /api/integrations/whatsapp/messages
       ▼
┌──────────────────┐          ┌────────────────────────┐
│   nmve.io        │  webhook │   FastAPI webhook       │
│   WhatsApp API   │─────────►│  POST /api/webhooks/   │
│   (Key 1)        │          │       whatsapp          │
└──────────────────┘          └────────────────────────┘
                                        │
                                        ▼
                               PostgreSQL (Render)
```

---

## 5. Dual API Key Architecture (CRITICAL)

> [!CAUTION]
> These two keys have DIFFERENT permission scopes. Mixing them causes HTTP 403 errors. The separation is enforced at **three layers** in code.

| | Key 1 — Messaging | Key 2 — Gateway |
|---|---|---|
| **Env var** | `WHATSAPP_MESSAGE_API_KEY` (alias: `WHATSAPP_API_KEY`) | `NMHIREX_GATEWAY_API_KEY` (alias: `NMHIREX_API_KEY`) |
| **Value prefix** | `wa_live_fb8308…` | `wa_live_a28795…` |
| **Scope / permission** | `whatsapp:send` | `candidates:write` |
| **Used for** | All outreach & confirmation WhatsApp messages | Only `/api/integrations/whatsapp/raw/add-candidate` |
| **Endpoint** | `https://nmve.io/whatsapp/api/integrations/whatsapp/messages` | `https://nmve.io/whatsapp/api/integrations/whatsapp/raw/add-candidate` |
| **Code file** | `tools_function.py → _send_whatsapp_payload()` | `gateway_client.py → GatewayClient` |

**Three-layer `automate` key exclusion** (must never reach the gateway):
1. `api.py` — `candidate_input.pop("automate", None)` before calling `add_candidate()`
2. `gateway_service.py` — `candidate_input.pop("automate", None)` at entry of `add_candidate()`
3. `tools_function.py` — `automate` param is never included in the dict passed downstream

---

## 6. Candidate Recruitment Flow

### 6a. `automate: "yes"` (immediate send — default)

```
Recruiter POSTs /api/outreach/send-array
  { candidates: [...], automate: "yes" }
        │
        ▼
  For each candidate:
    1. Upsert Candidate record (by phone/email)
    2. Upsert JobCandidate (status = CONTACTED)
    3. Send WhatsApp template "candidate_shortlisted_outreach" via Key 1
        │
        ▼
  Candidate replies on WhatsApp
        │
        ▼
  Webhook POST /api/webhooks/whatsapp
    → Detect intent (INTERESTED / NOT_INTERESTED)
    → If INTERESTED: send scheduling link
        https://nmhirex.onrender.com/schedule/{jobCandidateId}
        │
        ▼
  Candidate opens scheduling page, picks date + time
        │
        ▼
  POST /api/scheduling/confirm
    → Calls Gateway (Key 2) → /raw/add-candidate
    → Gets registrationUrl = https://interview.teckvalley.com/
    → Saves registrationUrl to job_candidates.registration_url
    → Sends confirmation WhatsApp via Key 1 with interview link
    → Sets recruitment_status = INTERVIEW_SCHEDULED
        │
        ▼
  APScheduler fires 24h & 1h reminders
```

### 6b. `automate: "no"` (manual queue)

```
Recruiter POSTs /api/outreach/send-array
  { candidates: [...], automate: "no" }
        │
        ▼
  For each candidate:
    1. Upsert Candidate record
    2. Upsert JobCandidate (status = PENDING_OUTREACH)
    3. NO WhatsApp message sent
        │
        ▼
  Recruiter visits /outreach/pending
    → Sees queued candidates table
    → Selects one/multiple/all
    → Clicks WhatsApp logo button
        │
        ▼
  POST /api/outreach/send-pending
    { job_candidate_ids: [...] }
        │
        ▼
  Flow continues same as automate:yes from "Send WhatsApp" step
```

---

## 7. Database Schema

Five active tables (defined in `backend/app/models.py`):

### `users`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | String(150) | |
| `email` | String(255) unique | |
| `role` | String(30) | `RECRUITER` or `ADMIN` |
| `status` | String(30) | `PENDING`, `APPROVED`, `ACTIVE` |
| `is_active` | Boolean | |
| `password_hash` | String(255) | bcrypt |
| `created_at`, `updated_at` | DateTime | |

### `jobs`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `created_by` | UUID FK→users | |
| `title` | String(255) | Job role name |
| `status` | String(50) | `ACTIVE`, `CLOSED` |
| `requisition_id` | String(255) | External ref (nullable) |

### `candidates`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | String(255) | |
| `email` | String(255) | |
| `phone` | String(50) indexed | Stored with country code, e.g. `917439717970` |
| `current_company` | String(255) | |
| `current_role` | String(255) | |
| `total_experience_years` | Numeric(5,2) | |
| `normalized_profile` | JSONB | |

### `job_candidates` *(primary workflow state machine)*
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Used as `request_id` to Gateway |
| `job_id` | UUID FK→jobs CASCADE | |
| `candidate_id` | UUID FK→candidates CASCADE | |
| `recruitment_status` | String(50) indexed | See status lifecycle below |
| `interview_scheduled_at` | DateTime | |
| `interview_link` | Text | Usually `registrationUrl` from Gateway |
| `registration_url` | Text | Copy of Gateway `registrationUrl` |
| `request_id` | String(255) | `job_candidates.id` as string |
| `requisition_id` | String(255) | External numeric ID (sent as int to Gateway) |
| `reschedule_token` | String(36) unique | One-time reschedule UUID |
| `reminder_24h_sent` | Boolean | APScheduler guard |
| `reminder_1h_sent` | Boolean | APScheduler guard |

**Recruitment status lifecycle:**
```
NEW
 ├─► PENDING_OUTREACH   (automate: "no")
 └─► CONTACTED          (WhatsApp outreach sent)
       ├─► NOT_INTERESTED
       └─► INTERESTED
             └─► INTERVIEW_LINK_SENT
                   └─► INTERVIEW_SCHEDULED
                         ├─► INTERVIEW_COMPLETED
                         ├─► FAILED
                         └─► SKIPPED
```

### `candidate_contacts` *(outreach & reply log)*
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `job_candidate_id` | UUID FK→job_candidates CASCADE | |
| `channel` | String(50) | `WHATSAPP` |
| `message_type` | String(100) | `OUTREACH`, `CONFIRMATION`, `REMINDER`, etc. |
| `message` | Text | Actual message body |
| `status` | String(50) | `SENT`, `DELIVERED`, `READ`, `FAILED` |
| `response_intent` | String(50) | `INTERESTED`, `NOT_INTERESTED`, `RESCHEDULE` |
| `response_text` | Text | Raw reply from candidate |

---

## 8. Backend API Reference

Base URL: `https://nmhirex.onrender.com/api`  
All authenticated endpoints require `Authorization: Bearer <JWT>` header.

### Health
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | None | Liveness check |

### Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | None | Register new recruiter (form data) |
| POST | `/auth/login` | None | Login → returns JWT |

### User / Jobs
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/user/jobs` | JWT | List recruiter's jobs |
| GET | `/user/jobs/{job_id}/candidates` | JWT | Candidates for a specific job |
| GET | `/user/dashboard` | JWT | Dashboard stats |
| GET | `/user/outreach` | JWT | Outreach history |
| GET | `/user/candidates` | JWT | All candidates for recruiter |
| POST | `/user/jobs/{job_id}/candidates/{candidate_id}/status` | JWT | Update single candidate status |
| POST | `/user/jobs/{job_id}/candidates/bulk-status` | JWT | Bulk status update |

### Admin
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/admin/jobs` | JWT (ADMIN) | All jobs across all recruiters |
| GET | `/admin/jobs/{job_id}/candidates` | JWT (ADMIN) | Candidates for any job |

### Outreach
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/outreach/send-array` | Optional JWT | Send outreach to candidate array |
| POST | `/outreach/invite` | Optional JWT | Alias for `/send-array` |
| GET | `/outreach/pending` | JWT | Get PENDING_OUTREACH queue |
| POST | `/outreach/send-pending` | JWT | Send WhatsApp to pending candidates |

**`/outreach/send-array` payload schema:**
```json
{
  "candidates": [
    {
      "name": "Rahul Sharma",
      "role": "Software Engineer",
      "no": "917439717970",
      "email": "rahul@gmail.com",
      "company": "Acme Corp",
      "experience": "5",
      "automate": "yes"
    }
  ],
  "job_id": "<UUID optional>",
  "company_name": "Acme Corp",
  "automate": "yes"
}
```
> `automate` can be set globally on the outer object or per-candidate. Per-candidate takes precedence. **This key is never forwarded to the Gateway.**

### Scheduling (candidate-facing, no auth)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/scheduling/dates` | None | Available interview dates (next 8 days) |
| GET | `/scheduling/slots` | None | Available time slots for a date |
| POST | `/scheduling/confirm` | None | Confirm interview slot |
| GET | `/reschedule/{token}` | None | Fetch reschedule details by token |
| POST | `/reschedule/{token}` | None | Confirm reschedule |

### Webhooks
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/webhooks/whatsapp` | Secret header | nmve.io webhook for incoming replies |

### Gateway (WhatsApp Integration Pass-through)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET/POST | `/gateway/schedules` | None | List scheduled interviews from nmve.io |
| GET/POST | `/gateway/interview-results` | None | Interview results from nmve.io |
| GET | `/gateway/interviews-joined` | None | Schedules + results joined |
| POST | `/gateway/add-candidate` | None | Create candidate + schedule on nmve.io |
| POST | `/gateway/candidates` | None | Alias for `/gateway/add-candidate` |

---

## 9. Frontend Routes & Pages

| Path | File | Description |
|---|---|---|
| `/` or `/login` | `Login.jsx` | Email/password login |
| `/register` | `Register.jsx` | New recruiter self-registration |
| `/dashboard` | `Dashboard.jsx` | Recruiter job list + candidate stats |
| `/admin` | `AdminDashboard.jsx` | Admin view of all jobs/recruiters |
| `/candidates` | `Candidates.jsx` | Full candidate list with search |
| `/outreach` | `Outreach.jsx` | Outreach responses — WhatsApp reply log |
| `/outreach/send` | `OutreachSend.jsx` | **Main recruiter action** — paste/type candidates, send outreach |
| `/outreach/pending` | `PendingOutreach.jsx` | Manual queue — select & send WhatsApp for `automate:no` candidates |
| `/whatsapp-gateway` | `WhatsAppGateway.jsx` | View Gateway schedules + interview results |
| `/schedule/:candidateId` | `ScheduleInterview.jsx` | Candidate self-scheduling page (public) |
| `/reschedule/:token` | `Reschedule.jsx` | Candidate reschedule page (one-time token) |
| `/requisitions/:vereq/matches` | `TopCandidates.jsx` | Resume matching results view |

### `OutreachSend.jsx` — column schema

The table input mirrors the `/send-array` schema exactly:

| Column | API key | Notes |
|---|---|---|
| Name | `name` | |
| Role | `role` | |
| Phone | `no` | With country code, e.g. `917439717970` |
| Email | `email` | |
| Company | `company` | |
| Experience | `experience` | String (e.g. "5") |
| Automate | `automate` | Dropdown: `yes` (blue) / `no` (amber) |

---

## 10. Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host/nmhirex` |
| `JWT_SECRET_KEY` | Random secret for JWT signing | `super_secret_key` |
| `JWT_ALGORITHM` | JWT algo | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL | `60` |
| `WHATSAPP_MESSAGE_API_KEY` | **Key 1** — `whatsapp:send` scope | `wa_live_fb8308…` |
| `WHATSAPP_API_KEY` | Alias for Key 1 (backward compat) | same as above |
| `WHATSAPP_BASE_URL` | WhatsApp messages endpoint | `https://nmve.io/whatsapp/api/integrations/whatsapp/messages` |
| `WHATSAPP_STAGE_NUMBER` | Test phone number (without country code) | `7439717970` |
| `NMHIREX_GATEWAY_URL` | Gateway base URL (no trailing slash) | `https://nmve.io/whatsapp` |
| `NMHIREX_GATEWAY_API_KEY` | **Key 2** — `candidates:write` scope | `wa_live_a28795…` |
| `NMHIREX_API_KEY` | Alias for Key 2 | same as above |
| `NMHIREX_GATEWAY_TIMEOUT_SECONDS` | Gateway HTTP timeout | `25` |
| `NMHIREX_DEFAULT_REQUISITION_ID` | Fallback integer requisition ID | `506` |
| `FRONTEND_URL` | CORS allow-origin | `https://your-frontend.vercel.app` |
| `WEBHOOK_SECRET` | Optional secret for webhook verification | `random_string` |

### Frontend (`frontend/.env`)

| Variable | Description | Example |
|---|---|---|
| `VITE_API_BASE_URL` | Backend base URL (no trailing slash) | `https://nmhirex.onrender.com` |

---

## 11. Running Locally

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env           # Fill in real values
python init_db.py              # Creates tables (first time only)
uvicorn app.main:app --reload --port 8000
```

API docs available at: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
cp .env.example .env           # Set VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

App available at: `http://localhost:5173`

### Running Tests

```bash
cd backend
python test_dual_key_flow.py   # Key isolation + automate exclusion tests
```

> Always run tests before pushing — especially after changing `api.py`, `tools_function.py`, or `gateway_service.py`.

---

## 12. Deployment (Render)

| Service | Type | Branch | Auto-deploy |
|---|---|---|---|
| `nmhirex-backend` | Web Service (Python) | `main` | Yes — on every push |
| `nmhirex-db` | PostgreSQL | — | Managed by Render |

**Start command** (from `Procfile`):
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

**How to deploy:**
1. `git add . && git commit -m "your message"`
2. `git push origin main`
3. Render auto-detects the push and redeploys.
4. Monitor at: https://dashboard.render.com

**Frontend deployment:** Can be deployed to Vercel or Render Static Site.  
Set env var `VITE_API_BASE_URL=https://nmhirex.onrender.com` in the deployment config.

---

## 13. Key Constraints & Gotchas

> [!IMPORTANT]
> **`automate` key must NEVER reach the Gateway API.** It is stripped at three separate code layers. If you add a new code path that calls `add_candidate()`, always call `payload.pop("automate", None)` first.

> [!IMPORTANT]
> **`requisition_id` sent to Gateway must always be a positive integer**, not a UUID. The backend tries to parse it as int; if it fails it falls back to `NMHIREX_DEFAULT_REQUISITION_ID` (default: `506`).

> [!WARNING]
> **Key 1 is for messaging only. Key 2 is for `/addcandidates` only.** Swapping them results in HTTP 403 `INSUFFICIENT_SCOPE`. Never pass Key 2 to `_send_whatsapp_payload()`.

> [!NOTE]
> The fixed interview link / registration URL is always `https://interview.teckvalley.com/` as a fallback. The Gateway returns the real `registrationUrl` dynamically. The old domain `nminterview.com` is dead — do not use it.

> [!NOTE]
> Phone numbers must include country code (e.g. `917439717970` for India). The backend normalizes to last 10 digits for deduplication but stores the full number.

> [!NOTE]
> `git push` and `npm install` require `BypassSandbox: true` on Windows due to filesystem permission restrictions in the development sandbox.

---

## 14. Known Error Patterns & Fixes

| Error | Cause | Fix |
|---|---|---|
| `HTTP 403 INSUFFICIENT_SCOPE` on WhatsApp send | Key 2 used for messaging | Use `WHATSAPP_MESSAGE_API_KEY` (Key 1) for all `_send_whatsapp_payload()` calls |
| `HTTP 400 A positive requisition_id is required` | UUID string sent as `requisition_id` to Gateway | Parse to int; fallback to `NMHIREX_DEFAULT_REQUISITION_ID` |
| `fatal: Unable to create '.git/index.lock'` | Sandbox blocks `.git/` writes on Windows | Run `git add/commit/push` with `BypassSandbox: true` |
| Webhook not received | Wrong `WEBHOOK_SECRET` or Render not redeployed | Check Render logs; verify secret matches nmve.io webhook config |
| Frontend shows stale data | CORS mismatch or old `VITE_API_BASE_URL` | Verify `frontend/.env` points to live backend URL and rebuild |
| `EPERM mkdir` during npm install | Windows sandbox transient error | Re-run the same command up to 2 times |

