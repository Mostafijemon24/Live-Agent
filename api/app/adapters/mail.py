"""Mail adapters.

OutboxMailer (development only): writes each message to MAIL_OUTBOX_DIR as an
.eml file so a developer can open verification/reset links locally. Links are
NOT written to application logs. Config validation refuses this adapter in
production.
"""

from __future__ import annotations

import logging
import smtplib
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage as MimeMessage
from pathlib import Path

from app.core.config import Settings
from app.ports import EmailMessage

log = logging.getLogger("steward.mail")


def _mask(addr: str) -> str:
    local, _, domain = addr.partition("@")
    return f"{local[:1]}***@{domain}"


class OutboxMailer:
    def __init__(self, outbox: Path, sender: str) -> None:
        self.outbox = outbox
        self.sender = sender
        self.outbox.mkdir(parents=True, exist_ok=True, mode=0o700)

    def send(self, msg: EmailMessage) -> None:
        m = MimeMessage()
        m["From"] = self.sender
        m["To"] = msg.to
        m["Subject"] = msg.subject
        # 8bit keeps links readable and copy-pasteable when a developer opens the file.
        m.set_content(msg.text, cte="8bit")
        name = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.eml"
        path = self.outbox / name
        path.write_bytes(bytes(m))
        path.chmod(0o600)
        log.info("dev mail written to outbox file=%s to=%s subject=%r", name, _mask(msg.to), msg.subject)


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def send(self, msg: EmailMessage) -> None:
        m = MimeMessage()
        m["From"] = self.s.mail_from
        m["To"] = msg.to
        m["Subject"] = msg.subject
        m.set_content(msg.text)
        assert self.s.smtp_host, "SMTP_HOST is required for MAIL_BACKEND=smtp"
        with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=10) as smtp:
            if self.s.smtp_starttls:
                smtp.starttls()
            if self.s.smtp_username and self.s.smtp_password:
                smtp.login(self.s.smtp_username, self.s.smtp_password.get_secret_value())
            smtp.send_message(m)
        log.info("mail sent to=%s subject=%r", _mask(msg.to), msg.subject)


class DisabledMailer:
    def send(self, msg: EmailMessage) -> None:
        log.warning("mail backend disabled; message to=%s not sent", _mask(msg.to))


def build_mailer(settings: Settings) -> OutboxMailer | SmtpMailer | DisabledMailer:
    if settings.mail_backend == "outbox":
        return OutboxMailer(settings.mail_outbox_dir, settings.mail_from)
    if settings.mail_backend == "smtp":
        return SmtpMailer(settings)
    return DisabledMailer()
