import logging
import smtplib
from email.message import EmailMessage
from app.core.config import settings

logger = logging.getLogger(__name__)


def send_otp_email(email: str, otp: str) -> None:
    if settings.otp_delivery.lower() == "console":
        if settings.environment.lower() == "production":
            raise RuntimeError("Console OTP delivery is disabled in production")
        logger.warning("DEVELOPMENT ONLY OTP for %s: %s", email, otp)
        return

    if not (settings.smtp_user and settings.smtp_app_password and settings.smtp_from):
        raise RuntimeError("SMTP credentials are not configured")

    message = EmailMessage()
    message["Subject"] = "Your HEALTHSYNC-AI verification code"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        f"Your HEALTHSYNC-AI verification code is {otp}. "
        f"It expires in {settings.otp_ttl_minutes} minutes."
    )
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.login(settings.smtp_user, settings.smtp_app_password)
        smtp.send_message(message)
