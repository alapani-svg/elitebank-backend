from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils import timezone
from .models import User, Beneficiary, Notification
import re


# ── User profile (read) ───────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = [
            'id', 'email', 'full_name', 'phone_number',
            'avatar_url', 'language',
            'email_notifications', 'sms_alerts', 'two_factor_enabled',
            'balance_xaf', 'is_verified', 'date_joined', 'password_changed_at'
        ]
        read_only_fields = [
            'id', 'email', 'balance_xaf',
            'is_verified', 'date_joined', 'password_changed_at'
        ]


# ── Profile update (PATCH /api/auth/me/) ─────────────────────────────────────

class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = [
            'full_name', 'phone_number', 'avatar_url',
            'language', 'email_notifications', 'sms_alerts'
        ]

    def validate_phone_number(self, value):
        cleaned = re.sub(r'[^\d+]', '', value)
        if len(cleaned) < 9:
            raise serializers.ValidationError("Enter a valid phone number.")
        # Exclude current user from uniqueness check
        qs = User.objects.filter(phone_number=cleaned)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This phone number is already in use.")
        return cleaned


# ── Change password ───────────────────────────────────────────────────────────

class ChangePasswordSerializer(serializers.Serializer):
    current_password  = serializers.CharField(write_only=True)
    new_password      = serializers.CharField(write_only=True, min_length=8)
    confirm_password  = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        if not re.search(r'[a-zA-Z]', value):
            raise serializers.ValidationError("Password must contain at least one letter.")
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must contain at least one digit.")
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.password_changed_at = timezone.now()
        user.save()
        return user


# ── Toggle 2FA ────────────────────────────────────────────────────────────────

class TwoFactorSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()

    def save(self, **kwargs):
        user = self.context['request'].user
        user.two_factor_enabled = self.validated_data['enabled']
        user.save()
        return user


# ── Registration ──────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    password         = serializers.CharField(write_only=True, min_length=8,
                           style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True,
                           style={'input_type': 'password'})

    class Meta:
        model  = User
        fields = ['full_name', 'email', 'phone_number', 'password', 'password_confirm']

    def validate_full_name(self, value):
        cleaned = ' '.join(value.split())
        if len(cleaned) < 3:
            raise serializers.ValidationError("Full name must be at least 3 characters.")
        if User.objects.filter(full_name__iexact=cleaned).exists():
            raise serializers.ValidationError("A user with this name already exists.")
        return cleaned

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate_phone_number(self, value):
        cleaned = re.sub(r'[^\d+]', '', value)
        if len(cleaned) < 9:
            raise serializers.ValidationError("Enter a valid phone number.")
        if User.objects.filter(phone_number=cleaned).exists():
            raise serializers.ValidationError("This phone number is already in use.")
        return cleaned

    def validate_password(self, value):
        if not re.search(r'[a-zA-Z]', value):
            raise serializers.ValidationError("Password must contain at least one letter.")
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must contain at least one digit.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


# ── Login ─────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        email    = attrs.get('email', '').lower()
        password = attrs.get('password')
        user     = authenticate(
            request=self.context.get('request'),
            username=email, password=password
        )
        if not user:
            raise serializers.ValidationError(
                {"detail": "Invalid email or password. Please try again."}
            )
        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": "Your account has been deactivated. Contact support."}
            )
        attrs['user'] = user
        return attrs


# ── Password reset (forgot password) ─────────────────────────────────────────

class PasswordResetRequestSerializer(serializers.Serializer):
    """Step 1: user types their email. We always return 200 to avoid email
    enumeration. If the address exists, an email containing a signed token
    is dispatched."""
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Step 2: user POSTs the signed token + a new password."""
    token            = serializers.CharField(max_length=400)
    new_password     = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        if not re.search(r'[a-zA-Z]', value):
            raise serializers.ValidationError("Password must contain at least one letter.")
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must contain at least one digit.")
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError(
                {'confirm_password': "Passwords do not match."}
            )
        return attrs


# ── Beneficiaries ─────────────────────────────────────────────────────────────

class BeneficiarySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Beneficiary
        fields = ['id', 'name', 'identifier', 'category', 'provider', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        category = attrs.get('category', Beneficiary.Category.TRANSFER)
        provider = attrs.get('provider', '').strip().upper()
        identifier = attrs.get('identifier', '').strip()

        if category == Beneficiary.Category.AIRTIME:
            if provider not in ('MTN', 'ORANGE'):
                raise serializers.ValidationError(
                    {'provider': 'Airtime beneficiaries require provider MTN or ORANGE.'}
                )
            cleaned = re.sub(r'[\s\-]', '', identifier)
            if not re.match(r'^\+?237[0-9]{8,9}$', cleaned):
                raise serializers.ValidationError(
                    {'identifier': 'Enter a valid Cameroonian phone number.'}
                )
            attrs['identifier'] = cleaned

        elif category == Beneficiary.Category.BILL_PAYMENT:
            if provider not in ('ENEO', 'CAMWATER', 'CANAL+', 'CAMTEL'):
                raise serializers.ValidationError(
                    {'provider': 'Choose a valid bill provider (ENEO, CAMWATER, CANAL+, CAMTEL).'}
                )
            if not identifier or len(identifier) < 3:
                raise serializers.ValidationError(
                    {'identifier': 'Meter number / reference is required.'}
                )

        else:  # TRANSFER
            if '@' in identifier:
                pass  # email
            else:
                cleaned = re.sub(r'[\s\-]', '', identifier)
                attrs['identifier'] = cleaned

        attrs['provider'] = provider
        return attrs

    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Notification
        fields = [
            'id', 'kind', 'category', 'title', 'body',
            'action_url', 'read', 'read_at', 'created_at',
        ]
        read_only_fields = fields