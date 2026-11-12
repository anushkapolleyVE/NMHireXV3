"""Automated WhatsApp Interview Reminder Scheduler.

This module provides background scheduled reminder dispatches for upcoming interviews.
It is executed periodically (every 30 seconds) by an asynchronous background task
started in FastAPI's application lifespan (`main.py`).

Core Responsibilities:
1. Candidate Reminder Tracking:
   - 24-Hour Reminder: Dispatched exactly 24 hours before the scheduled interview.
   - 1-Hour Reminder: Dispatched exactly 1 hour before the scheduled interview.
2. Timezone Integrity:
   - Normalizes and compares timestamps against India Standard Time (IST / `Asia/Kolkata`)
     to ensure correct wall-clock matching regardless of deployment server location.
3. Multi-Worker Distributed Concurrency Control:
   - Uses atomic SQL UPDATE queries (`JobCandidate.reminder_24h_sent == False`) to claim
     the dispatch slot before calling external WhatsApp APIs.
   - Guarantees zero duplicate WhatsApp messages even when running across multiple workers
     or hybrid cloud environments (e.g. Render production + local instances).
4. Direct Rescheduling & Meeting Access:
   - Injects the assessment link (`https://interview.teckvalley.com/` or custom registration URL).
   - Injects a personalized one-click reschedule URL (`{FRONTEND_URL}/reschedule/{token}`).
5. Audit & History:
   - Logs every outbound message into `candidate_contacts` for tracking conversation history.
   - Rolls back atomic claim flags if WhatsApp delivery fails so it can be retried within the time window.
"""

import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import JobCandidate, Candidate, CandidateContact
from .tools_function import _send_whatsapp_text_message
from .config import settings


def check_interview_reminders():
    """Scan the database for upcoming interviews and send automated WhatsApp reminders.

    Detailed Workflow:
    1. Database Session & Timezone:
       - Opens a dedicated SQLAlchemy session from `SessionLocal()`.
       - Obtains the current wall-clock time in IST (`Asia/Kolkata`) stripped of timezone info
         for direct comparison with database `interview_scheduled_at` timestamps.
    2. Candidate Retrieval:
       - Queries all `JobCandidate` records where `recruitment_status == 'INTERVIEW_SCHEDULED'`
         and `interview_scheduled_at` is populated.
    3. 24-Hour Reminder Check:
       - Evaluates `target_24h = sched - 24 hours`.
       - If `now` is within the 2-minute window `[target_24h, target_24h + 2 minutes]` and `reminder_24h_sent == False`:
         a. Performs an atomic SQL update setting `reminder_24h_sent = True`.
         b. If another worker already claimed it (`claimed == 0`), skips execution.
         c. Formulates the reminder text including interview time, test link, and reschedule link.
         d. Calls `_send_whatsapp_text_message()` using WhatsApp Key 1.
         e. Records an outbound log entry into `candidate_contacts`.
         f. If delivery fails, resets `reminder_24h_sent = False` so the next pass can retry.
    4. 1-Hour Reminder Check:
       - Evaluates `target_1h = sched - 1 hour`.
       - If `now` is within the 2-minute window `[target_1h, target_1h + 2 minutes]` and `reminder_1h_sent == False`:
         a. Performs an atomic SQL update setting `reminder_1h_sent = True`.
         b. If claimed by another instance, skips execution.
         c. Formulates the reminder text with test link and reschedule link.
         d. Dispatches message via WhatsApp.
         e. Records contact log in `candidate_contacts`.
         f. Rolls back flag if delivery fails.
    5. Clean Cleanup:
       - Rolls back transaction on unexpected exception.
       - Closes database session in `finally` block to prevent connection pool exhaustion.

    Returns:
        None
    """
    db: Session = SessionLocal()
    try:
        # Current local wall-clock time in India (IST) matching scheduled interview times
        now = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)

        # Query all scheduled candidates with active interview timestamps
        candidates = db.query(JobCandidate).filter(
            JobCandidate.recruitment_status == "INTERVIEW_SCHEDULED",
            JobCandidate.interview_scheduled_at.isnot(None),
        ).all()

        for jc in candidates:
            candidate = db.get(Candidate, jc.candidate_id)
            if not candidate or not candidate.phone:
                continue

            # Convert UTC-aware timestamp from DB to IST wall-clock time (naive) for comparison
            IST = ZoneInfo("Asia/Kolkata")
            raw_sched = jc.interview_scheduled_at
            if raw_sched.tzinfo is not None:
                # DB returned UTC-aware datetime → convert to IST then strip tzinfo
                sched = raw_sched.astimezone(IST).replace(tzinfo=None)
            else:
                # Already naive (stored without tz info) → treat as IST directly
                sched = raw_sched

            # Target times for exact reminder dispatches
            target_24h = sched - datetime.timedelta(hours=24)
            target_1h = sched - datetime.timedelta(hours=1)

            # Sanitize and format interview link (replace legacy teams URLs with teckvalley test portal)
            interview_link_display = jc.interview_link
            if interview_link_display and "teams.microsoft.com" in interview_link_display:
                interview_link_display = "https://interview.teckvalley.com/"
            teams_part = f"\nInterview Link: {interview_link_display}" if interview_link_display else ""

            # Resolve public frontend URL for candidate reschedule link
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://nm-hire-xv-3-c4m5.vercel.app').rstrip('/')
            if not frontend_url or "localhost" in frontend_url or "127.0.0.1" in frontend_url:
                frontend_url = "https://nm-hire-xv-3-c4m5.vercel.app"

            # ----------------------------------------------------
            # 1. EXACTLY 24 HOURS BEFORE INTERVIEW
            # Example: If interview is at 3:00 PM tomorrow, triggers at 3:00 PM today.
            # ----------------------------------------------------
            if not jc.reminder_24h_sent:
                if target_24h <= now < (target_24h + datetime.timedelta(minutes=2)):
                    # ATOMIC CLAIM: Update flag to True immediately before making external API call.
                    # If another process/worker already updated it, claimed will be 0 and we skip.
                    claimed = db.query(JobCandidate).filter(
                        JobCandidate.id == jc.id,
                        JobCandidate.reminder_24h_sent == False,
                    ).update({JobCandidate.reminder_24h_sent: True}, synchronize_session=False)
                    db.commit()

                    if not claimed:
                        # Another instance (e.g. Render worker or local dev) already claimed this send!
                        continue

                    time_str = sched.strftime('%B %d, %Y at %I:%M %p')
                    if jc.reschedule_token:
                        link = f"{frontend_url}/reschedule/{jc.reschedule_token}"
                        msg = (
                            f"Reminder: Your interview is in 24 hours at {time_str}.{teams_part}\n\n"
                            f"To reschedule, visit: {link}"
                        )
                    else:
                        msg = f"Reminder: Your interview is in 24 hours at {time_str}.{teams_part}"

                    print(f"[SCHEDULER] Triggering exact 24h reminder for {candidate.phone} (Interview at {time_str})")
                    sent = _send_whatsapp_text_message(raw_phone=candidate.phone, text_message=msg)
                    if sent:
                        # Record successful outbound contact log
                        db.add(
                            CandidateContact(
                                job_candidate_id=jc.id,
                                channel="WHATSAPP",
                                message_type="OUTBOUND",
                                message=msg,
                                provider="NMVE",
                                status="SENT",
                                sent_at=datetime.datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None),
                            )
                        )
                        db.commit()
                        print(f"[SCHEDULER] Exact 24h reminder sent successfully to {candidate.phone}")
                    else:
                        # Rollback claim if delivery failed so it can be retried on next loop pass
                        db.query(JobCandidate).filter(JobCandidate.id == jc.id).update(
                            {JobCandidate.reminder_24h_sent: False}, synchronize_session=False
                        )
                        db.commit()
                        print(f"[SCHEDULER] Failed to deliver 24h reminder to {candidate.phone}")

            # ----------------------------------------------------
            # 2. EXACTLY 1 HOUR BEFORE INTERVIEW
            # Example: If interview is at 3:00 PM today, triggers at 2:00 PM today.
            # ----------------------------------------------------
            if not jc.reminder_1h_sent:
                if target_1h <= now < (target_1h + datetime.timedelta(minutes=2)):
                    # ATOMIC CLAIM: Update flag to True immediately before making external API call.
                    claimed = db.query(JobCandidate).filter(
                        JobCandidate.id == jc.id,
                        JobCandidate.reminder_1h_sent == False,
                    ).update({JobCandidate.reminder_1h_sent: True}, synchronize_session=False)
                    db.commit()

                    if not claimed:
                        # Another instance already claimed this send!
                        continue

                    time_str = sched.strftime('%I:%M %p')
                    if jc.reschedule_token:
                        link = f"{frontend_url}/reschedule/{jc.reschedule_token}"
                        msg = (
                            f"Reminder: Your interview is in 1 hour at {time_str}.{teams_part}\n\n"
                            f"To reschedule, visit: {link}"
                        )
                    else:
                        msg = f"Reminder: Your interview is in 1 hour at {time_str}.{teams_part}"

                    print(f"[SCHEDULER] Triggering exact 1h reminder for {candidate.phone} (Interview at {time_str})")
                    sent = _send_whatsapp_text_message(raw_phone=candidate.phone, text_message=msg)
                    if sent:
                        # Record successful outbound contact log
                        db.add(
                            CandidateContact(
                                job_candidate_id=jc.id,
                                channel="WHATSAPP",
                                message_type="OUTBOUND",
                                message=msg,
                                provider="NMVE",
                                status="SENT",
                                sent_at=datetime.datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None),
                            )
                        )
                        db.commit()
                        print(f"[SCHEDULER] Exact 1h reminder sent successfully to {candidate.phone}")
                    else:
                        # Rollback claim if delivery failed so it can be retried
                        db.query(JobCandidate).filter(JobCandidate.id == jc.id).update(
                            {JobCandidate.reminder_1h_sent: False}, synchronize_session=False
                        )
                        db.commit()
                        print(f"[SCHEDULER] Failed to deliver 1h reminder to {candidate.phone}")

    except Exception as e:
        print(f"[SCHEDULER ERROR] Error in check_interview_reminders: {e}")
        db.rollback()
    finally:
        # Guarantee session closure to avoid database connection pool exhaustion
        db.close()
