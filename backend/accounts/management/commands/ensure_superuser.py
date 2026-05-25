"""
Bootstrap a superuser from environment variables.

Idempotent: if a superuser already exists with the given email, just ensure
is_staff + is_superuser + is_active are True. Otherwise create one.

Designed to run on every Render deploy as part of buildCommand, since the
free tier has no Shell access for `createsuperuser`.

Required env vars (set on Render dashboard):
    BOOTSTRAP_ADMIN_EMAIL
    BOOTSTRAP_ADMIN_PASSWORD

Optional env vars (sensible defaults):
    BOOTSTRAP_ADMIN_NAME         (default: "Elite Bank Admin")
    BOOTSTRAP_ADMIN_PHONE        (default: "+237600000000")

If BOOTSTRAP_ADMIN_EMAIL or BOOTSTRAP_ADMIN_PASSWORD is missing, the command
is a silent no-op so it doesn't break the build.
"""

import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Create or promote a superuser from BOOTSTRAP_ADMIN_* env vars."

    def handle(self, *args, **options):
        email    = os.environ.get('BOOTSTRAP_ADMIN_EMAIL', '').strip().lower()
        password = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD', '')
        name     = os.environ.get('BOOTSTRAP_ADMIN_NAME',  'Elite Bank Admin').strip()
        phone    = os.environ.get('BOOTSTRAP_ADMIN_PHONE', '+237600000000').strip()

        if not email or not password:
            self.stdout.write(self.style.WARNING(
                'ensure_superuser: BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD '
                'not set — skipping.'
            ))
            return

        user = User.objects.filter(email__iexact=email).first()

        if user:
            changed = []
            if not user.is_staff:     user.is_staff     = True; changed.append('is_staff')
            if not user.is_superuser: user.is_superuser = True; changed.append('is_superuser')
            if not user.is_active:    user.is_active    = True; changed.append('is_active')
            if changed:
                user.save(update_fields=changed)
                self.stdout.write(self.style.SUCCESS(
                    f'ensure_superuser: promoted existing user {email} '
                    f'({", ".join(changed)} set to True).'
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f'ensure_superuser: superuser {email} already exists — nothing to do.'
                ))
            return

        User.objects.create_superuser(
            email=email,
            password=password,
            full_name=name,
            phone_number=phone,
        )
        self.stdout.write(self.style.SUCCESS(
            f'ensure_superuser: created new superuser {email}.'
        ))
