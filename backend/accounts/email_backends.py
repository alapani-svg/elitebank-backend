"""
Custom Django email backend that delivers via the Brevo (Sendinblue)
transactional REST API instead of SMTP.

Activated when the BREVO_API_KEY env var is set and EMAIL_BACKEND in
settings points at this class. Otherwise settings.py falls back to
Django's standard SMTP backend (Gmail) or the console backend (dev).

The backend implements the same `send_messages(messages)` contract as
Django's BaseEmailBackend, so every existing `send_mail(...)` /
EmailMultiAlternatives call across the codebase works unchanged - OTPs,
password-reset codes, transaction notifications, everything.
"""
import logging
import re
import requests
from email.utils import parseaddr
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailBackend(BaseEmailBackend):
    """Sends Django EmailMessage instances via Brevo's transactional REST API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.api_key = getattr(settings, "BREVO_API_KEY", "") or ""
        self.timeout = getattr(settings, "BREVO_TIMEOUT", 15)

    def send_messages(self, email_messages):
        if not self.api_key:
            logger.warning("BREVO_API_KEY is empty; no emails will be sent.")
            return 0
        if not email_messages:
            return 0

        sent = 0
        for message in email_messages:
            try:
                self._send_one(message)
                sent += 1
            except Exception as exc:
                logger.warning("Brevo send failed for %s: %s", message.to, exc)
                if not self.fail_silently:
                    raise
        return sent

    def _send_one(self, message):
        """Translate one EmailMessage into a Brevo /v3/smtp/email payload."""
        name, addr = parseaddr(message.from_email or settings.DEFAULT_FROM_EMAIL)
        sender = {"email": addr or "noreply@elite-bank.cm"}
        if name:
            sender["name"] = name

        to_list = [{"email": e} for e in message.to if e]
        if not to_list:
            return

        payload = {
            "sender":  sender,
            "to":      to_list,
            "subject": message.subject or "(no subject)",
        }

        if getattr(message, "cc", None):
            payload["cc"] = [{"email": e} for e in message.cc]
        if getattr(message, "bcc", None):
            payload["bcc"] = [{"email": e} for e in message.bcc]
        if getattr(message, "reply_to", None):
            ra_name, ra_addr = parseaddr(message.reply_to[0])
            reply_to = {"email": ra_addr}
            if ra_name:
                reply_to["name"] = ra_name
            payload["replyTo"] = reply_to

        text_body = message.body or ""
        html_body = ""
        for content, mimetype in getattr(message, "alternatives", []) or []:
            if mimetype == "text/html":
                html_body = content
                break

        is_html_primary = (
            getattr(message, "content_subtype", "plain") == "html"
            or bool(re.search(r"<\s*html", text_body, re.IGNORECASE))
        )
        if is_html_primary and not html_body:
            html_body = text_body
            text_body = re.sub(r"<[^>]+>", "", text_body).strip()

        if text_body:
            payload["textContent"] = text_body
        if html_body:
            payload["htmlContent"] = html_body
        if not text_body and not html_body:
            payload["textContent"] = " "

        response = requests.post(
            BREVO_ENDPOINT,
            headers={
                "api-key":      self.api_key,
                "accept":       "application/json",
                "content-type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Brevo HTTP {response.status_code}: {response.text[:300]}"
            )
        logger.info("Brevo: delivered %s -> %s", message.subject, [e['email'] for e in to_list])
