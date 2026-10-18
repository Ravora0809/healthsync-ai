"""Send due reminder emails once per reminder/due date using configured SMTP."""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AuditEvent, Reminder, User

logger = logging.getLogger(__name__)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _already_sent(db: Session, user_id, reminder_id: str, due_date: str) -> bool:
    events = db.query(AuditEvent).filter(
        AuditEvent.owner_user_id == user_id,
        AuditEvent.action == "reminder_email_sent",
    ).all()
    return any(
        (event.details or {}).get("reminder_id") == reminder_id
        and (event.details or {}).get("due_date") == due_date
        for event in events
    )


def send_due_reminder_emails(db: Session, now: datetime | None = None) -> int:
    """Send email for due/overdue reminders once; return the number sent.

    SMTP settings are read from the backend environment. If SMTP is not configured,
    this function safely does nothing and leaves reminders visible in the app.
    """
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_app_password):
        return 0

    now_utc = _as_utc(now or datetime.now(timezone.utc))
    sent_count = 0
    rows = db.query(Reminder, User).join(User, User.id == Reminder.owner_user_id).filter(
        Reminder.is_completed.is_(False),
        Reminder.due_at <= now_utc,
    ).all()

    for reminder, user in rows:
        due = _as_utc(reminder.due_at)
        due_date = due.date().isoformat()
        reminder_id = str(reminder.id)
        if _already_sent(db, user.id, reminder_id, due_date):
            continue

        is_today = due.date() == now_utc.date()
        subject = f"HEALTHSYNC-AI reminder: {reminder.title}"
        due_label = "today" if is_today else f"was due on {due.strftime('%d %b %Y')}"
        body = (
            f"Hello {user.full_name},\n\n"
            f"This is your HEALTHSYNC-AI reminder.\n\n"
            f"Reminder: {reminder.title}\n"
            f"Due: {due.strftime('%d %b %Y at %H:%M UTC')} ({due_label})\n"
            f"Details: {reminder.description or 'No additional details provided.'}\n\n"
            "Please review the original record and confirm any medical schedule with your healthcare professional.\n\n"
            "This is an automated reminder from your HEALTHSYNC-AI workspace."
        )
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.smtp_from or settings.smtp_user
        message["To"] = user.email
        message.set_content(body)
        try:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.login(settings.smtp_user, settings.smtp_app_password)
                smtp.send_message(message)
            db.add(AuditEvent(
                owner_user_id=user.id,
                action="reminder_email_sent",
                details={"reminder_id": reminder_id, "due_date": due_date, "recipient": user.email},
            ))
            db.commit()
            sent_count += 1
        except Exception as exc:  # SMTP outages must not stop the reminder scheduler.
            db.rollback()
            logger.warning("Reminder email failed for reminder %s (%s): %s", reminder_id, user.email, exc)

    return sent_count
