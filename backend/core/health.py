"""Lightweight liveness/readiness probes."""
from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods


@never_cache
@require_http_methods(["GET", "HEAD"])
def health(_request):
    """Quick liveness probe — returns immediately."""
    return JsonResponse({'status': 'ok', 'service': 'elite-bank-api'})


@never_cache
@require_http_methods(["GET", "HEAD"])
def readiness(_request):
    """Readiness probe — verifies the DB connection works."""
    try:
        connections['default'].cursor().execute('SELECT 1')
        db_ok = True
        db_err = None
    except OperationalError as e:
        db_ok = False
        db_err = str(e)

    payload = {
        'status':   'ok' if db_ok else 'degraded',
        'service':  'elite-bank-api',
        'checks':   {'database': 'ok' if db_ok else 'fail'},
    }
    if db_err:
        payload['error'] = db_err
    return JsonResponse(payload, status=200 if db_ok else 503)
