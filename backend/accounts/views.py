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

    Creates the user, marks them verified, and returns JWT tokens immediately.
    User management (suspend, manual verification override, etc.) happens in
    the Django admin panel.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        user.is_verified = True
        user.save(update_fields=['is_verified'])

        tokens = get_tokens_for_user(user)
        return Response({
            'message': 'Account created successfully.',
            'user':    UserSerializer(user).data,
            'tokens':  tokens,
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
    user's `is_verified` flag is set to True and they can log in normally.
    Returns NO JWT — the frontend should redirect to /login.
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

        return Response({
            'message': 'Email verified successfully. You can now sign in.',
            'email':   user.email,
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

class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password-reset/request/  body: { "email": "..." }

    Always returns 200 — never reveals whether the email exists, to prevent
    account enumeration. If the email matches an active user, a signed
    one-hour token is emailed to them.
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
            user = None

        if user:
            from .services.password_reset import make_token, send_password_reset_email
            token = make_token(user)
            send_password_reset_email(user, token)

            # Also drop an in-app notification so it shows in the bell next login.
            try:
                from .services.notifications import notify
                notify(
                    user, 'SECURITY', 'INFO',
                    title='Password reset requested',
                    body='If this was not you, ignore this notification.',
                )
            except Exception:
                pass

        return Response(
            {'detail': 'If an account exists for that email, we just sent a reset link.'},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """
    POST /api/auth/password-reset/confirm/
      body: { "token": "...", "new_password": "...", "confirm_password": "..." }

    Verifies the signed token (≤ 1 hour old), sets the new password, and
    drops an in-app notification + email confirmation.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        from .services.password_reset import consume_token
        user = consume_token(serializer.validated_data['token'])
        if user is None:
            return Response(
                {'detail': 'This reset link is invalid or has expired. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data['new_password'])
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