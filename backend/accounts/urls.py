from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView, RegisterVerifyView, RegisterResendView,
    LoginView, LogoutView, MeView,
    ChangePasswordView, TwoFactorView, AvatarUploadView,
    PasswordResetRequestView, PasswordResetVerifyOTPView, PasswordResetConfirmView,
    OTPVerifyView, OTPResendView,
    BeneficiaryListCreateView, BeneficiaryDetailView,
    NotificationListView, NotificationMarkReadView, NotificationDeleteView,
)

urlpatterns = [
    path('register/',                RegisterView.as_view(),              name='auth-register'),
    path('register/verify/',         RegisterVerifyView.as_view(),        name='auth-register-verify'),
    path('register/resend/',         RegisterResendView.as_view(),        name='auth-register-resend'),
    path('login/',                   LoginView.as_view(),                 name='auth-login'),
    path('logout/',                  LogoutView.as_view(),                name='auth-logout'),
    path('me/',                      MeView.as_view(),                    name='auth-me'),
    path('password-reset/request/',     PasswordResetRequestView.as_view(),    name='auth-pw-reset-request'),
    path('password-reset/verify-otp/',  PasswordResetVerifyOTPView.as_view(),  name='auth-pw-reset-verify-otp'),
    path('password-reset/confirm/',     PasswordResetConfirmView.as_view(),    name='auth-pw-reset-confirm'),
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
    path('2fa/',                     TwoFactorView.as_view(),             name='auth-2fa'),
    path('2fa/verify/',              OTPVerifyView.as_view(),             name='auth-2fa-verify'),
    path('2fa/resend/',              OTPResendView.as_view(),             name='auth-2fa-resend'),
    path('avatar/',          AvatarUploadView.as_view(),   name='auth-avatar'),
    path('token/refresh/',   TokenRefreshView.as_view(),   name='token-refresh'),

    # Beneficiaries
    path('beneficiaries/',           BeneficiaryListCreateView.as_view(), name='beneficiary-list'),
    path('beneficiaries/<uuid:pk>/', BeneficiaryDetailView.as_view(),     name='beneficiary-detail'),

    # Notifications
    path('notifications/',                    NotificationListView.as_view(),      name='notification-list'),
    path('notifications/mark-all-read/',      NotificationMarkReadView.as_view(),  name='notification-mark-all-read'),
    path('notifications/<uuid:pk>/read/',     NotificationMarkReadView.as_view(),  name='notification-mark-read'),
    path('notifications/<uuid:pk>/delete/',   NotificationDeleteView.as_view(),    name='notification-delete'),
]