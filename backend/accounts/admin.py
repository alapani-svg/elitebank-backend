from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import User, Beneficiary, Notification, OTPChallenge

# ── Admin site branding ───────────────────────────────────────────────────────
admin.site.site_header = "Elite Bank Administration"
admin.site.site_title  = "Elite Bank Admin"
admin.site.index_title = "Administration Dashboard"


# ── Forms for the admin ───────────────────────────────────────────────────────

class UserCreationForm(forms.ModelForm):
    """Used in the "Add User" admin page."""
    password1 = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        label='Password confirmation',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Enter the same password as before, for verification.',
    )

    class Meta:
        model  = User
        fields = ('email', 'full_name', 'phone_number')

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("The two password fields didn't match.")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    """Used in the "Change User" admin page."""
    password = ReadOnlyPasswordHashField(
        label='Password',
        help_text=(
            'Raw passwords are not stored. '
            'You can change it using <a href="../password/">this form</a>.'
        ),
    )

    class Meta:
        model  = User
        fields = '__all__'


# ── User admin ────────────────────────────────────────────────────────────────

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form     = UserChangeForm
    add_form = UserCreationForm

    # ── List view ─────────────────────────────────────────────────────────────
    list_display = (
        'avatar_thumbnail', 'full_name', 'email', 'phone_number',
        'balance_formatted', 'verified_badge', 'notifications_badge',
        'is_active', 'is_staff', 'date_joined',
    )
    list_display_links = ('full_name', 'email')
    list_filter  = (
        'is_active', 'is_staff', 'is_superuser',
        'is_verified', 'email_notifications', 'sms_alerts',
        'two_factor_enabled', 'language',
    )
    search_fields = ('email', 'full_name', 'phone_number')
    ordering      = ('-date_joined',)
    list_per_page = 25

    # ── Detail view ───────────────────────────────────────────────────────────
    readonly_fields = (
        'id', 'date_joined', 'updated_at',
        'avatar_preview', 'password_changed_at',
    )

    fieldsets = (
        (_('Identity'), {
            'fields': ('id', 'full_name', 'email', 'phone_number'),
        }),
        (_('Avatar'), {
            'fields':   ('avatar_preview', 'avatar_url'),
            'classes':  ('collapse',),
        }),
        (_('Security'), {
            'fields': ('password', 'password_changed_at', 'two_factor_enabled'),
        }),
        (_('Account & Balance'), {
            'fields': ('balance_xaf', 'is_verified', 'is_active', 'language'),
        }),
        (_('Notification Preferences'), {
            'fields': ('email_notifications', 'sms_alerts'),
        }),
        (_('Staff Permissions'), {
            'fields':  ('is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',),
        }),
        (_('Timestamps'), {
            'fields': ('date_joined', 'updated_at'),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'full_name', 'email', 'phone_number',
                'password1', 'password2',
                'is_staff', 'is_superuser',
            ),
        }),
    )

    # ── Bulk actions ──────────────────────────────────────────────────────────
    actions = [
        'action_verify', 'action_unverify',
        'action_activate', 'action_deactivate',
        'action_enable_email_notifications', 'action_disable_email_notifications',
    ]

    # ── Custom columns ────────────────────────────────────────────────────────

    def avatar_thumbnail(self, obj):
        avatar = getattr(obj, 'avatar_url', '') or ''
        if avatar:
            return format_html(
                '<img src="{}" width="32" height="32" '
                'style="border-radius:50%;object-fit:cover;border:2px solid #D4AF37;" />',
                avatar,
            )
        name = getattr(obj, 'full_name', '') or ''
        initials = ''.join(w[0].upper() for w in name.split()[:2]) or '?'
        return format_html(
            '<div style="width:32px;height:32px;border-radius:50%;background:#D4AF37;'
            'color:#12110F;display:inline-flex;align-items:center;justify-content:center;'
            'font-size:11px;font-weight:900;line-height:1;">{}</div>',
            initials,
        )
    avatar_thumbnail.short_description = ''

    def avatar_preview(self, obj):
        avatar = getattr(obj, 'avatar_url', '') or ''
        if avatar:
            return format_html(
                '<img src="{}" width="90" height="90" '
                'style="border-radius:50%;object-fit:cover;border:3px solid #D4AF37;" />'
                '<br/><small style="color:#999;word-break:break-all;">{}</small>',
                avatar, avatar,
            )
        return format_html('<span style="color:#999;">No avatar uploaded.</span>')
    avatar_preview.short_description = 'Current Avatar'

    def balance_formatted(self, obj):
        bal = obj.balance_xaf or 0
        amount = f'{bal:,.0f}'
        if bal > 0:
            return format_html(
                '<strong style="color:#28a745;">XAF {}</strong>', amount
            )
        return format_html(
            '<span style="color:#dc3545;">XAF {}</span>', amount
        )
    balance_formatted.short_description = 'Balance (XAF)'
    balance_formatted.admin_order_field = 'balance_xaf'

    def verified_badge(self, obj):
        if obj.is_verified:
            return format_html(
                '<span style="background:#d4edda;color:#155724;padding:2px 8px;'
                'border-radius:10px;font-size:11px;font-weight:700;">✓ Verified</span>'
            )
        return format_html(
            '<span style="background:#f8d7da;color:#721c24;padding:2px 8px;'
            'border-radius:10px;font-size:11px;font-weight:700;">✗ Unverified</span>'
        )
    verified_badge.short_description = 'KYC'
    verified_badge.admin_order_field = 'is_verified'

    def notifications_badge(self, obj):
        parts = []
        if obj.email_notifications:
            parts.append('<span title="Email alerts ON" style="color:#28a745;">✉</span>')
        if obj.sms_alerts:
            parts.append('<span title="SMS alerts ON" style="color:#0d6efd;">📱</span>')
        return format_html(' '.join(parts)) if parts else format_html(
            '<span style="color:#ccc;">—</span>'
        )
    notifications_badge.short_description = 'Alerts'

    # ── Actions ───────────────────────────────────────────────────────────────

    @admin.action(description='✓ Mark selected users as Verified')
    def action_verify(self, request, queryset):
        n = queryset.update(is_verified=True)
        self.message_user(request, f'{n} user(s) marked as verified.', messages.SUCCESS)

    @admin.action(description='✗ Mark selected users as Unverified')
    def action_unverify(self, request, queryset):
        n = queryset.update(is_verified=False)
        self.message_user(request, f'{n} user(s) marked as unverified.', messages.WARNING)

    @admin.action(description='▶ Activate selected users')
    def action_activate(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, f'{n} user(s) activated.', messages.SUCCESS)

    @admin.action(description='⏸ Deactivate selected users')
    def action_deactivate(self, request, queryset):
        n = queryset.exclude(pk=request.user.pk).update(is_active=False)
        self.message_user(
            request,
            f'{n} user(s) deactivated. (Your own account is never deactivated.)',
            messages.WARNING,
        )

    @admin.action(description='✉ Enable email notifications')
    def action_enable_email_notifications(self, request, queryset):
        n = queryset.update(email_notifications=True)
        self.message_user(request, f'Email notifications enabled for {n} user(s).', messages.SUCCESS)

    @admin.action(description='✉ Disable email notifications')
    def action_disable_email_notifications(self, request, queryset):
        n = queryset.update(email_notifications=False)
        self.message_user(request, f'Email notifications disabled for {n} user(s).', messages.WARNING)


# ── Beneficiary admin ─────────────────────────────────────────────────────────

@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display  = ('name', 'identifier', 'category', 'provider', 'owner', 'created_at')
    list_filter   = ('category', 'provider', 'created_at')
    search_fields = ('name', 'identifier', 'owner__email', 'owner__full_name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    list_per_page = 25


# ── Notification admin ────────────────────────────────────────────────────────

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ('title', 'user', 'category', 'kind_badge', 'read', 'created_at')
    list_filter   = ('kind', 'category', 'read', 'created_at')
    search_fields = ('title', 'body', 'user__email', 'user__full_name')
    readonly_fields = ('id', 'created_at', 'read_at')
    list_per_page = 50
    actions       = ['action_mark_read', 'action_mark_unread']

    def kind_badge(self, obj):
        colors_map = {
            'INFO':    ('#cfe2ff', '#0d47a1'),
            'SUCCESS': ('#d4edda', '#155724'),
            'WARNING': ('#fff3cd', '#856404'),
            'ERROR':   ('#f8d7da', '#721c24'),
        }
        bg, fg = colors_map.get(obj.kind, ('#eee', '#333'))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;border-radius:10px;'
            'font-size:11px;font-weight:700;">{}</span>',
            bg, fg, obj.kind,
        )
    kind_badge.short_description = 'Kind'

    @admin.action(description='Mark selected as read')
    def action_mark_read(self, request, queryset):
        from django.utils import timezone
        n = queryset.filter(read=False).update(read=True, read_at=timezone.now())
        self.message_user(request, f'{n} notification(s) marked as read.', messages.SUCCESS)

    @admin.action(description='Mark selected as unread')
    def action_mark_unread(self, request, queryset):
        n = queryset.filter(read=True).update(read=False, read_at=None)
        self.message_user(request, f'{n} notification(s) marked as unread.', messages.WARNING)


# ── OTP Challenge admin ───────────────────────────────────────────────────────

@admin.register(OTPChallenge)
class OTPChallengeAdmin(admin.ModelAdmin):
    list_display    = ('user', 'state_badge', 'attempts', 'expires_at', 'created_at')
    list_filter     = ('created_at', 'expires_at')
    search_fields   = ('user__email', 'user__full_name', 'id')
    readonly_fields = ('id', 'user', 'code_hash', 'expires_at',
                       'consumed_at', 'attempts', 'created_at')
    list_per_page   = 50
    ordering        = ('-created_at',)
    actions         = ['action_invalidate']

    def state_badge(self, obj):
        from django.utils import timezone
        if obj.consumed_at:
            bg, fg, txt = '#e2e3e5', '#495057', 'CONSUMED'
        elif obj.expires_at < timezone.now():
            bg, fg, txt = '#f8d7da', '#721c24', 'EXPIRED'
        else:
            bg, fg, txt = '#d4edda', '#155724', 'LIVE'
        return format_html(
            '<span style="background:{};color:{};padding:2px 9px;border-radius:10px;'
            'font-size:11px;font-weight:700;">{}</span>',
            bg, fg, txt,
        )
    state_badge.short_description = 'State'

    @admin.action(description='Invalidate selected challenges (mark consumed)')
    def action_invalidate(self, request, queryset):
        from django.utils import timezone
        n = queryset.filter(consumed_at__isnull=True).update(consumed_at=timezone.now())
        self.message_user(request, f'{n} challenge(s) invalidated.', messages.WARNING)
