from django.contrib import admin
from django.urls import path, include

from drf_spectacular.views import (
    SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView,
)

from .health import health, readiness

urlpatterns = [
    # Django admin mounted at the root, so https://elite-bank-api.onrender.com/
    # serves the admin login directly (no redirect, no /admin/ prefix).
    path('', admin.site.urls),

    # Health probes
    path('healthz/',  health,    name='health'),
    path('readyz/',   readiness, name='readiness'),

    # API docs
    path('api/schema/',         SpectacularAPIView.as_view(),                                     name='schema'),
    path('api/docs/',           SpectacularSwaggerView.as_view(url_name='schema'),                name='swagger-ui'),
    path('api/redoc/',          SpectacularRedocView.as_view(url_name='schema'),                  name='redoc'),

    path('api/auth/',         include('accounts.urls')),
    path('api/transactions/', include('transactions.urls')),
]
