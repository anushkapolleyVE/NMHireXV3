import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import JobCandidate, Candidate, CandidateContact
from .tools_function import _send_whatsapp_text_message
from .config import settings


def check_interview_reminders():
    """
    Checks for upcoming interviews and sends WhatsApp reminders:
    1. Exactly 24 hours before the interview (e.g., at 3:00 PM today for tomorrow 3:00 PM)
    2. Exactly 1 hour before the interview (e.g., at 2:00 PM today for today 3:00 PM)
    """
    db: Session = SessionLocal()
    try:
        # Current local wall-clock time in India (IST) matching scheduled interview times
        now = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)

        candidates = db.query(JobCandidate).filter(
            JobCandidate.recruitment_status == "INTERVIEW_SCHEDULED",
            JobCandidate.interview_scheduled_at.isnot(None),
        ).all()

        for jc in candidates:
            candidate = db.get(Candidate, jc.candidate_id)
            if not candidate or not candidate.phone:
                continue

            # Strip tzinfo to compare direct wall-clock times
            sched = jc.interview_scheduled_at.replace(tzinfo=None)
            
            # Target times for exact reminder dispatches
            target_24h = sched - datetime.timedelta(hours=24)
            target_1h = sched - datetime.timedelta(hours=1)

            teams_part = f"\nTeams Link: {jc.interview_link}" if jc.interview_link else ""
            frontend_url = getattr(settings, 'FRONTEND_URL', 'https://nm-hire-xv-3-c4m5.vercel.app').rstrip('/')
            if not frontend_url or "localhost" in frontend_url or "127.0.0.1" in frontend_url:
                frontend_url = "https://nm-hire-xv-3-c4m5.vercel.app"

            # ----------------------------------------------------
            # 1. EXACTLY 24 HOURS BEFORE
            # If interview is at 3:00 PM tomorrow, triggers at 3:00 PM today.
            # Never triggers before 3:00 PM (now < target_24h).
            # ----------------------------------------------------
            if not jc.reminder_24h_sent:
                if target_24h <= now < (target_24h + datetime.timedelta(minutes=2)):
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
                        jc.reminder_24h_sent = True
                        db.add(
                            CandidateContact(
                                job_candidate_id=jc.id,
                                channel="WHATSAPP",
                                message_type="OUTBOUND",
                                message=msg,
                                provider="NMVE",
                                status="SENT",
                                sent_at=datetime.datetime.utcnow(),
                            )
                        )
                        db.commit()
                        print(f"[SCHEDULER] Exact 24h reminder sent successfully to {candidate.phone}")
                    else:
                        print(f"[SCHEDULER] Failed to deliver 24h reminder to {candidate.phone}")

            # ----------------------------------------------------
            # 2. EXACTLY 1 HOUR BEFORE
            # If interview is at 3:00 PM today, triggers at 2:00 PM today.
            # Never triggers before 2:00 PM (now < target_1h).
            # ----------------------------------------------------
            if not jc.reminder_1h_sent:
                if target_1h <= now < (target_1h + datetime.timedelta(minutes=2)):
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
                        jc.reminder_1h_sent = True
                        db.add(
                            CandidateContact(
                                job_candidate_id=jc.id,
                                channel="WHATSAPP",
                                message_type="OUTBOUND",
                                message=msg,
                                provider="NMVE",
                                status="SENT",
                                sent_at=datetime.datetime.utcnow(),
                            )
                        )
                        db.commit()
                        print(f"[SCHEDULER] Exact 1h reminder sent successfully to {candidate.phone}")
                    else:
                        print(f"[SCHEDULER] Failed to deliver 1h reminder to {candidate.phone}")

    except Exception as e:
        print(f"[SCHEDULER ERROR] Error in check_interview_reminders: {e}")
        db.rollback()
    finally:
        db.close()
