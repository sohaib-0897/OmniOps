"""Password reset delivery. Never log or return the reset URL."""

import asyncio
import os
import smtplib
import uuid
from email.message import EmailMessage
from pathlib import Path

from app.core.config import settings


def _deliver(email: str, url: str) -> None:
    if not settings.SMTP_HOST:
        if settings.ENVIRONMENT.lower() in {"production", "prod", "staging"}:
            raise RuntimeError("Password reset mail transport is unavailable.")
        outbox = settings.STORAGE_DIR / "dev-password-reset-outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        path = outbox / f"{uuid.uuid4()}.txt"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"To: {email}\nReset link: {url}\n")
        return
    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = email
    message["Subject"] = "Reset your OmniOps password"
    message.set_content(f"Use this link to reset your OmniOps password. It expires in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes.\n\n{url}\n\nIf you did not request this, you can ignore this email.")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        if settings.SMTP_STARTTLS:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
        smtp.send_message(message)


async def deliver_password_reset(email: str, url: str) -> None:
    await asyncio.to_thread(_deliver, email, url)
