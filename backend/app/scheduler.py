import datetime
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import JobCandidate, Candidate
from .tools_function import _send_whatsapp_payload, _clean_whatsapp_phone
from .config import settings
import uuid

def send_whatsapp_message(phone: str, message: str):
    payload = {
        "to": _clean_whatsapp_phone(phone),
        "type": "text",
        "text": {
            "body": message
        }
    }
    # This might need adjustment depending on the actual expected payload structure
    # of the whatsapp provider used in _send_whatsapp_payload.
    _send_whatsapp_payload(payload)

def check_interview_reminders():
    db: Session = SessionLocal()
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # 24h reminder
        start_24h = now + datetime.timedelta(hours=23, minutes=30)
        end_24h = now + datetime.timedelta(hours=24, minutes=30)
        
        candidates_24h = db.query(JobCandidate).filter(
            JobCandidate.interview_scheduled_at.between(start_24h, end_24h),
            JobCandidate.reminder_24h_sent == False,
            JobCandidate.reschedule_token.isnot(None)
        ).all()
        
        for jc in candidates_24h:
            candidate = db.get(Candidate, jc.candidate_id)
            if candidate and candidate.phone:
                link = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/reschedule/{jc.reschedule_token}"
                msg = f"Reminder: Your interview is in 24 hours at {jc.interview_scheduled_at.strftime('%B %d, %Y at %I:%M %p')}. To reschedule, visit: {link}"
                send_whatsapp_message(candidate.phone, msg)
                jc.reminder_24h_sent = True
        
        # 1h reminder
        start_1h = now + datetime.timedelta(minutes=30)
        end_1h = now + datetime.timedelta(minutes=90)
        
        candidates_1h = db.query(JobCandidate).filter(
            JobCandidate.interview_scheduled_at.between(start_1h, end_1h),
            JobCandidate.reminder_1h_sent == False,
            JobCandidate.reschedule_token.isnot(None)
        ).all()
        
        for jc in candidates_1h:
            candidate = db.get(Candidate, jc.candidate_id)
            if candidate and candidate.phone:
                link = f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/reschedule/{jc.reschedule_token}"
                msg = f"Reminder: Your interview is in 1 hour at {jc.interview_scheduled_at.strftime('%I:%M %p')}. Teams Link: {jc.interview_link}. To reschedule, visit: {link}"
                send_whatsapp_message(candidate.phone, msg)
                jc.reminder_1h_sent = True

        db.commit()
    finally:
        db.close()
