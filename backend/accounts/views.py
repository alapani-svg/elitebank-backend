from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from rest_framework_simplejwt.tokens import RefreshToken
import traceback
import sys

from django.utils import timezone
from .models import Beneficiary, Notification
from .serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer,
    ProfileUpdateSerializer, ChangePasswordSerializer, TwoFactorSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    BeneficiarySerializer, NotificationSerializer,
)


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access':  str(refresh.access_token),
    }


class RegisterView(APIView):
    """
    POST /api/auth/register/  body: { email, full_name, phone_number, password, password_confirm }

    Creates the user with is_verified=False and emails a 6-digit OTP to prove
    they own the email address. Returns NO JWT — the frontend must POST the
    code to /api/auth/register/verify/ to receive tokens.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        user.is_verified = False
        user.save(update_fields=['is_verified'])

        from .services.otp import issue_challenge, send_otp, mask_email
        challenge, code = issue_challenge(user)
        send_otp(user, code)

        return Response({
            'message':      'Account created. Please enter the 6-digit code we just emailed you.',
            'requires_otp': True,
            'purpose':      'register',
            'challenge_id': str(challenge.id),
            'masked_email': mask_email(user.email),
            'email':        user.email,
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """
    POST /api/auth/login/  body: { "email": "...", "password": "..." }

    Validates credentials and returns JWT tokens. No OTP / 2FA — pure JWT auth.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data, context={'request': request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

        user   = serializer.validated_data['user']
        tokens = get_tokens_for_user(user)
        return Response({
            'message': 'Login successful.',
            'user':    UserSerializer(user).data,
            'tokens':  tokens,
        }, status=status.HTTP_200_OK)


class OTPVerifyView(APIView):
    """
    POST /api/auth/2fa/verify/  body: { "challenge_id": "...", "code": "123456" }

    Verifies a one-time password issued by `LoginView` for a 2FA-enabled user.
    On success, returns JWT tokens identical to a normal login.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        challenge_id = (request.data.get('challenge_id') or '').strip()
        code         = (request.data.get('code') or '').strip()

        if not challenge_id or not code:
            return Response(
                {'detail': 'challenge_id and code are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .services.otp import verify_challenge
        challenge, error = verify_challenge(challenge_id, code)
        if challenge is None:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)

        user   = challenge.user
        tokens = get_tokens_for_user(user)

        try:
            from .services.notifications import notify
            notify(
                user, 'SECURITY', 'INFO',
                title='New sign-in',
                body='You just signed in to Elite Bank with two-factor authentication.',
            )
        except Exception:
            pass

        return Response({
            'message': 'Login successful.',
            'user':    UserSerializer(user).data,
            'tokens':  tokens,
        }, status=status.HTTP_200_OK)


class RegisterVerifyView(APIView):
    """
    POST /api/auth/register/verify/  body: { challenge_id, code }

    Confirms the OTP that was emailed during registration. On success the
    user's `is_verified` flag is set to True AND JWT tokens are returned so
    the frontend can log them in immediately (no second login round-trip).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        challenge_id = (request.data.get('challenge_id') or '').strip()
        code         = (request.data.get('code') or '').strip()

        if not challenge_id or not code:
            return Response(
                {'detail': 'challenge_id and code are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .services.otp import verify_challenge
        challenge, error = verify_challenge(challenge_id, code)
        if challenge is None:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)

        user = challenge.user
        user.is_verified = True
        user.save(update_fields=['is_verified'])

        try:
            from .services.notifications import notify
            notify(
                user, 'ACCOUNT', 'SUCCESS',
                title='Welcome to Elite Bank',
                body='Your email address has been verified. You can now sign in.',
            )
        except Exception:
            pass

        tokens = get_tokens_for_user(user)
        return Response({
            'message':  'Email verified successfully.',
            'user':     UserSerializer(user).data,
            'tokens':   tokens,
            'verified': True,
        }, status=status.HTTP_200_OK)


class RegisterResendView(APIView):
    """
    POST /api/auth/register/resend/  body: { email }

    Re-issues a fresh registration OTP. The user is identified by email
    (since they don't have a session yet). Always returns 200 to avoid
    leaking which emails exist. Only fires when the user is not yet verified.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response(
                {'detail': 'email is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from accounts.models import User as UserModel
        try:
            user = UserModel.objects.get(email__iexact=email, is_active=True, is_verified=False)
        except UserModel.DoesNotExist:
            # Silent success — don't reveal whether the address exists.
            return Response({
                'message':      'If your account needs verification, a new code has been sent.',
                'masked_email': '',
            }, status=status.HTTP_200_OK)

        from .services.otp import issue_challenge, send_otp, mask_email
        challenge, code = issue_challenge(user)
        send_otp(user, code)

        return Response({
            'message':      'A new verification code has been sent to your email.',
            'challenge_id': str(challenge.id),
            'masked_email': mask_email(user.email),
        }, status=status.HTTP_200_OK)


class OTPResendView(APIView):
    """
    POST /api/auth/2fa/resend/  body: { "challenge_id": "..." }

    Re-issues a fresh OTP for the same user. The old challenge is invalidated.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        challenge_id = (request.data.get('challenge_id') or '').strip()
        if not challenge_id:
            return Response(
                {'detail': 'challenge_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from accounts.models import OTPChallenge
        try:
            old = OTPChallenge.objects.select_related('user').get(pk=challenge_id)
        except (OTPChallenge.DoesNotExist, ValueError):
            return Response(
                {'detail': 'This session has expired. Please log in again.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Invalidate the old challenge so only the latest code works.
        if not old.consumed_at:
            from django.utils import timezone
            old.consumed_at = timezone.now()
            old.save(update_fields=['consumed_at'])

        from .services.otp import issue_challenge, send_otp, mask_email
        new, code = issue_challenge(old.user)
        send_otp(old.user, code)

        return Response({
            'challenge_id': str(new.id),
            'masked_email': mask_email(old.user.email),
            'message':      'A new verification code has been sent to your email.',
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    POST /api/auth/logout/  body: { "refresh": "<token>" }
    Blacklists the refresh token so it can't be used again.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get('refresh')
        if not refresh:
            return Response(
                {'detail': 'refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            from rest_framework_simplejwt.tokens import RefreshToken
            token = RefreshToken(refresh)
            token.blacklist()
        except Exception:
            return Response(
                {'detail': 'Invalid or expired refresh token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'message': 'Logged out.'}, status=status.HTTP_200_OK)


# ── Password reset (forgot password) ──────────────────────────────────────────

_RESET_TOKEN_SALT   = 'elite-bank.password-reset'
_RESET_TOKEN_MAXAGE = 10 * 60


class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password-reset/request/  body: { "email": "..." }

    Issues a 6-digit OTPChallenge for the user and emails the code. Returns
    the challenge_id so the frontend can drive the verify-otp step.
    Always returns 200 even if the email is unknown (no account enumeration).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']

        from accounts.models import User as UserModel
        try:
            user = UserModel.objects.get(email__iexact=email, is_active=True)
        except UserModel.DoesNotExist:
            return Response({
                'message':      'If an account exists for that email, a 6-digit code has been sent.',
                'challenge_id': '',
                'masked_email': '',
                'email':        email,
            }, status=status.HTTP_200_OK)

        from .services.otp import issue_challenge, send_otp, mask_email
        challenge, code = issue_challenge(user)
        send_otp(user, code)

        try:
            from .services.notifications import notify
            notify(
                user, 'SECURITY', 'INFO',
                title='Password reset requested',
                body='A 6-digit code was emailed to reset your password. If this was not you, ignore this message.',
            )
        except Exception:
            pass

        return Response({
            'message':      'A 6-digit code has been sent to your email.',
            'challenge_id': str(challenge.id),
            'masked_email': mask_email(user.email),
            'email':        user.email,
        }, status=status.HTTP_200_OK)


class PasswordResetVerifyOTPView(APIView):
    """
    POST /api/auth/password-reset/verify-otp/
      body: { "challenge_id": "...", "code": "123456" }

    Verifies the OTP and returns a short-lived (10 min) signed reset_token
    that the frontend hands back to /password-reset/confirm/ together with
    the new password.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        challenge_id = (request.data.get('challenge_id') or '').strip()
        code         = (request.data.get('code') or '').strip()

        if not challenge_id or not code:
            return Response(
                {'detail': 'challenge_id and code are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .services.otp import verify_challenge
        challenge, error = verify_challenge(challenge_id, code)
        if challenge is None:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)

        from django.core import signing
        reset_token = signing.dumps(
            {'user_id': str(challenge.user.id), 'purpose': 'password_reset'},
            salt=_RESET_TOKEN_SALT,
        )

        return Response({
            'message':     'Code verified. You can now set a new password.',
            'reset_token': reset_token,
            'verified':    True,
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """
    POST /api/auth/password-reset/confirm/
      body: { "reset_token": "...", "new_password": "...", "confirm_password": "..." }

    Validates the signed reset_token (max age 10 minutes), enforces the
    password policy, and writes the new password.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        reset_token      = request.data.get('reset_token') or request.data.get('token') or ''
        new_password     = request.data.get('new_password') or ''
        confirm_password = request.data.get('confirm_password') or ''

        if not reset_token:
            return Response({'detail': 'reset_token is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if new_password != confirm_password:
            return Response({'confirm_password': ['Passwords do not match.']},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(new_password) < 8:
            return Response({'new_password': ['Password must be at least 8 characters.']},
                            status=status.HTTP_400_BAD_REQUEST)
        import re
        if not (re.search(r'[a-zA-Z]', new_password) and re.search(r'\d', new_password)):
            return Response({'new_password': ['Password must contain both letters and digits.']},
                            status=status.HTTP_400_BAD_REQUEST)

        from django.core import signing
        try:
            payload = signing.loads(reset_token, salt=_RESET_TOKEN_SALT, max_age=_RESET_TOKEN_MAXAGE)
        except signing.SignatureExpired:
            return Response({'detail': 'This reset link has expired. Please restart the flow.'},
                            status=status.HTTP_400_BAD_REQUEST)
        except signing.BadSignature:
            return Response({'detail': 'Invalid reset token. Please restart the flow.'},
                            status=status.HTTP_400_BAD_REQUEST)

        if payload.get('purpose') != 'password_reset':
            return Response({'detail': 'Invalid reset token.'},
                            status=status.HTTP_400_BAD_REQUEST)

        from accounts.models import User as UserModel
        try:
            user = UserModel.objects.get(pk=payload['user_id'], is_active=True)
        except UserModel.DoesNotExist:
            return Response({'detail': 'Account no longer exists or has been deactivated.'},
                            status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        from django.utils import timezone
        user.password_changed_at = timezone.now()
        user.save(update_fields=['password', 'password_changed_at'])

        try:
            from .services.notifications import notify
            notify(
                user, 'SECURITY', 'SUCCESS',
                title='Password reset',
                body='Your Elite Bank password was successfully reset.',
            )
        except Exception:
            pass

        return Response(
            {'message': 'Your password has been reset. You can now log in with the new password.'},
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Profile updated successfully.',
                'user':    UserSerializer(request.user).data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            from .services.notifications import notify
            notify(
                request.user, 'SECURITY', 'WARNING',
                title='Password changed',
                body='Your password was changed. If this was not you, contact support immediately.',
            )
            return Response({'message': 'Password changed successfully.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TwoFactorView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = TwoFactorSerializer(
            data=request.data, context={'request': request}
        )
        if serializer.is_valid():
            user = serializer.save()
            status_text = 'enabled' if user.two_factor_enabled else 'disabled'
            from .services.notifications import notify
            notify(
                user, 'SECURITY', 'INFO',
                title=f'Two-factor authentication {status_text}',
                body=f'2FA has been {status_text} on your account.',
            )
            return Response({
                'message': f'Two-factor authentication {status_text}.',
                'two_factor_enabled': user.two_factor_enabled
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AvatarUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            file = request.FILES.get('avatar')

            if not file:
                return Response(
                    {'detail': 'No file provided. Send a file with key "avatar".'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Accept any image type
            if not file.content_type.startswith('image/'):
                return Response(
                    {'detail': 'Invalid file type. Please upload an image file.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Max 10MB
            if file.size > 10 * 1024 * 1024:
                return Response(
                    {'detail': 'File too large. Maximum size is 10MB.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            from .services.storage import upload_avatar
            url = upload_avatar(file, str(request.user.id))
            request.user.avatar_url = url
            request.user.save()

            return Response({
                'message':    'Avatar updated successfully.',
                'avatar_url': url
            }, status=status.HTTP_200_OK)

        except Exception as e:
            # Print full traceback to Django terminal so we can debug
            traceback.print_exc(file=sys.stdout)
            return Response(
                {'detail': f'Upload failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


# ── Beneficiaries ─────────────────────────────────────────────────────────────

class BeneficiaryListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/auth/beneficiaries/         → list current user's saved beneficiaries
    POST /api/auth/beneficiaries/         → save a new beneficiary
    """
    serializer_class   = BeneficiarySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Beneficiary.objects.filter(owner=self.request.user)
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category.upper())
        return qs


class BeneficiaryDetailView(generics.RetrieveDestroyAPIView):
    """
    GET    /api/auth/beneficiaries/<id>/  → retrieve
    DELETE /api/auth/beneficiaries/<id>/  → delete
    """
    serializer_class   = BeneficiarySerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field       = 'pk'

    def get_queryset(self):
        return Beneficiary.objects.filter(owner=self.request.user)


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationListView(generics.ListAPIView):
    """
    GET /api/auth/notifications/[?unread=1&limit=N]
    Returns the user's notifications, newest first.
    Always includes an `unread_count` in the response envelope.
    """
    serializer_class   = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class   = None

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get('unread') in ('1', 'true', 'True'):
            qs = qs.filter(read=False)
        return qs

    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        try:
            limit = int(request.query_params.get('limit', '50'))
        except ValueError:
            limit = 50
        sliced = qs[: max(1, min(limit, 200))]
        unread_count = Notification.objects.filter(user=request.user, read=False).count()
        data = NotificationSerializer(sliced, many=True).data
        return Response({
            'results':      data,
            'unread_count': unread_count,
            'total':        qs.count(),
        })


class NotificationMarkReadView(APIView):
    """
    POST /api/auth/notifications/<id>/read/    → mark a single notification read
    POST /api/auth/notifications/mark-all-read/ → mark every notification read
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        if pk:
            try:
                n = Notification.objects.get(pk=pk, user=request.user)
            except Notification.DoesNotExist:
                return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
            n.mark_read()
            return Response(NotificationSerializer(n).data)

        # Mark all
        Notification.objects.filter(user=request.user, read=False).update(
            read=True, read_at=timezone.now()
        )
        return Response({'detail': 'All notifications marked as read.'})


class NotificationDeleteView(generics.DestroyAPIView):
    """DELETE /api/auth/notifications/<id>/"""
    permission_classes = [permissions.IsAuthenticated]
    lookup_field       = 'pk'

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)