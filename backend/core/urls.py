from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import path, include
from django.views.decorators.cache import never_cache

from drf_spectacular.views import (
    SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView,
)

from .health import health, readiness


@never_cache
def root_to_admin(_request):
    return HttpResponseRedirect('/admin/login/')


urlpatterns = [
    # Root → admin login. The admin stays at /admin/ to avoid the URL
    # resolver swallowing /api/* and /healthz/ paths (which happened when
    # admin was mounted at the empty prefix).
    path('', root_to_admin, name='root'),

    path('admin/', admin.site.urls),

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
