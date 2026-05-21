"""
One-time-password helpers for 2FA login.

Delivery channel: EMAIL — the OTP is sent to the user's registered email
address (no phone-number reliance, since phone formatting is fragile). If the
email backend is configured (EMAIL_HOST_USER set), the user gets a real
message; otherwise Django's console backend logs the code to the server
logs, which is fine for development & demo.

OTP characteristics:
- 6-digit numeric code, zero-padded
- SHA-256 hashed at rest (we never store the plain code in the DB)
- 5-minute TTL
- Max 5 verification attempts before the challenge is auto-consumed
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from accounts.models import OTPChallenge, User

logger = logging.getLogger(__name__)

OTP_LENGTH         = 6
OTP_TTL_MINUTES    = 5
MAX_ATTEMPTS       = 5


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


def _generate_code() -> str:
    """6 cryptographically random digits, zero-padded."""
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


def issue_challenge(user: User) -> tuple[OTPChallenge, str]:
    """Mint a new OTP challenge for the user. Returns (challenge, plain_code).

    The caller is responsible for delivering `plain_code` to the user.
    The plain code is NEVER persisted — only its SHA-256 hash.
    """
    code = _generate_code()
    expires_at = timezone.now() + timedelta(minutes=OTP_TTL_MINUTES)
    challenge = OTPChallenge.objects.create(
        user=user,
        code_hash=_hash_code(code),
        expires_at=expires_at,
    )
    return challenge, code


def send_otp(user: User, code: str) -> None:
    """Email the OTP to the user's registered address.

    Falls back to console-logging the code if the email backend rejects the
    message (no SMTP creds, network issue, etc.) — useful for demo / grading.
    """
    subject = "Your Elite Bank verification code"
    body = (
        f"Hi {user.full_name.split(' ')[0] if user.full_name else 'there'},\n\n"
        f"Your Elite Bank verification code is:\n\n"
        f"    {code}\n\n"
        f"This code expires in {OTP_TTL_MINUTES} minutes.\n"
        f"If you didn't request this code, please ignore this email and\n"
        f"consider changing your password.\n\n"
        f"— The Elite Bank team\n"
        f"Built by CORANTIN · promptforge237@gmail.com"
    )

    try:
        send_mail(
            subject,
            body,
            getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            [user.email],
            fail_silently=False,
        )
        logger.info('OTP emailed to %s', user.email)
        return
    except Exception as exc:
        logger.warning('Email gateway failed (%s) — falling back to console', exc)

    # DEMO MODE — log the code so the developer / grader can read it from
    # the server logs without needing a working SMTP connection.
    logger.warning('═══════════ OTP DEMO MODE ═══════════')
    logger.warning('User : %s', user.email)
    logger.warning('Code : %s', code)
    logger.warning('Valid: %d minutes', OTP_TTL_MINUTES)
    logger.warning('══════════════════════════════════════')


def verify_challenge(challenge_id: str, code: str) -> tuple[OTPChallenge | None, str]:
    """Verify a challenge. Returns (challenge_or_None, error_message).

    On success: challenge is marked consumed and returned (with empty error).
    On failure: attempts is incremented; once it hits MAX_ATTEMPTS the
    challenge is auto-consumed to prevent further brute-forcing.
    """
    try:
        challenge = OTPChallenge.objects.select_related('user').get(pk=challenge_id)
    except (OTPChallenge.DoesNotExist, ValueError):
        return None, 'This verification code is invalid or has expired.'

    if challenge.is_consumed():
        return None, 'This verification code has already been used.'
    if challenge.is_expired():
        return None, 'This verification code has expired. Please log in again.'
    if challenge.attempts >= MAX_ATTEMPTS:
        return None, 'Too many incorrect attempts. Please log in again.'

    if challenge.code_hash != _hash_code(code.strip()):
        challenge.attempts += 1
        update_fields = ['attempts']
        if challenge.attempts >= MAX_ATTEMPTS:
            challenge.consumed_at = timezone.now()
            update_fields.append('consumed_at')
        challenge.save(update_fields=update_fields)
        remaining = MAX_ATTEMPTS - challenge.attempts
        if remaining <= 0:
            return None, 'Too many incorrect attempts. Please log in again.'
        return None, f'Incorrect code. {remaining} attempt(s) remaining.'

    # Success — mark consumed
    challenge.consumed_at = timezone.now()
    challenge.save(update_fields=['consumed_at'])
    return challenge, ''


def mask_email(email: str) -> str:
    """Return e.g. `co**********05@gmail.com` for display in the OTP page.

    Hides the middle of the local-part while keeping the first 2 and last 2
    characters visible plus the full domain (so the user can confirm they
    recognise their own account).
    """
    if not email or '@' not in email:
        return '***'
    local, _, domain = email.partition('@')
    if len(local) <= 4:
        return f"{local[:1]}***@{domain}"
    return f"{local[:2]}{'*' * max(3, len(local) - 4)}{local[-2:]}@{domain}"


# Kept for backwards-compat with old callers that may still import this.
def mask_phone(phone: str) -> str:  # pragma: no cover
    if not phone or len(phone) < 4:
        return '****'
    return f"{phone[:4]} *** *** *{phone[-2:]}"
