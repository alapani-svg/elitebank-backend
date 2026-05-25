from pathlib import Path
from datetime import timedelta
import os

#  .env loader 
try:
    from decouple import config as _cfg
except ImportError:
    _BASE = Path(__file__).resolve().parent.parent
    _env_file = _BASE / '.env'
    if _env_file.exists():
        with open(_env_file, encoding='utf-8') as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _k, _, _v = _line.partition('=')
                    os.environ.setdefault(_k.strip(), _v.strip())

    def _cfg(key, default='', cast=None):          # type: ignore[misc]
        val = os.environ.get(key, default)
        if cast is bool:
            return str(val).lower() in ('true', '1', 'yes')
        if cast is not None:
            try:
                return cast(val)
            except (ValueError, TypeError):
                return default
        return val

BASE_DIR = Path(__file__).resolve().parent.parent

#  Security 
SECRET_KEY = _cfg('SECRET_KEY', default='django-insecure-change-me-in-production-use-env-var')
DEBUG      = _cfg('DEBUG', default='True', cast=bool)

ALLOWED_HOSTS = [h.strip() for h in _cfg('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')]

#  Apps 
INSTALLED_APPS = [
    # Jazzmin must come BEFORE django.contrib.admin
    'jazzmin',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',

    # Local
    'accounts',
    'transactions',
]

#  Middleware 
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',          # must be first
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',     # serve static in prod
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]




_frontend_urls = [u.strip() for u in _cfg(
    'FRONTEND_URL', default='http://localhost:4200'
).split(',') if u.strip()]
CORS_ALLOWED_ORIGINS = list({
    'http://localhost:4200',
    *_frontend_urls,
})


CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.vercel\.app$",
]
CSRF_TRUSTED_ORIGINS = [*_frontend_urls, 'https://elite-bank-cm.vercel.app', 'https://elite-bank-api.onrender.com']

ROOT_URLCONF = 'core.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
        ],
    },
}]

WSGI_APPLICATION = 'core.wsgi.application'

#  Database 
# Locally: SQLite. On Render: read DATABASE_URL (auto-injected for the linked
# Postgres instance) via dj-database-url.
_database_url = _cfg('DATABASE_URL', default='')
if _database_url:
    try:
        import dj_database_url
        DATABASES = {
            'default': dj_database_url.parse(_database_url, conn_max_age=600, ssl_require=True),
        }
    except ImportError:
        # dj-database-url not installed (local dev w/o prod deps) — fall back.
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': BASE_DIR / 'db.sqlite3',
            }
        }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

#  Auth 
AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─ DRF 
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

#  OpenAPI / Swagger 
SPECTACULAR_SETTINGS = {
    'TITLE':       'Elite Bank API',
    'DESCRIPTION': (
        'REST API for Elite Bank — Cameroon Digital Wealth.\n\n'
        'Authenticate via `POST /api/auth/login/`, then pass `Authorization: '
        'Bearer <access_token>` on subsequent requests. Every transactional '
        'endpoint pre-records a PENDING transaction so even failed attempts '
        'leave an audit trail.'
    ),
    'VERSION':                 '1.0.0',
    'SERVE_INCLUDE_SCHEMA':    False,
    'CONTACT':                 {'name': 'CORANTIN (Elite Bank)', 'email': 'promptforge237@gmail.com'},
    'COMPONENT_SPLIT_REQUEST': True,
    'TAGS': [
        {'name': 'Auth',           'description': 'Registration, login, JWT, profile, security'},
        {'name': 'Beneficiaries',  'description': 'Saved recipients for transfers / airtime / bills'},
        {'name': 'Notifications',  'description': 'In-app notification feed'},
        {'name': 'Transactions',   'description': 'Transfer / Deposit / Withdrawal / Bill / Airtime'},
        {'name': 'Statements',     'description': 'PDF / CSV export'},
        {'name': 'Health',         'description': 'Liveness & readiness probes'},
    ],
    # Hide health probes from the schema (they're for orchestrators, not API consumers)
    'PREPROCESSING_HOOKS': [],
    'SCHEMA_PATH_PREFIX': '/api/',
}

# ─ Simple JWT 
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':       timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME':      timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':       True,
    'BLACKLIST_AFTER_ROTATION':    True,
    'AUTH_HEADER_TYPES':           ('Bearer',),
    'USER_ID_FIELD':               'id',
    'USER_ID_CLAIM':               'user_id',
}

#  Internationalisation 
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Africa/Douala'
USE_I18N      = True
USE_TZ        = True

STATIC_URL      = 'static/'
STATIC_ROOT     = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

#  Production security defaults 
# Only enabled when DEBUG=False so dev stays HTTP-friendly.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER  = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE    = True
    CSRF_COOKIE_SECURE       = True
    SECURE_SSL_REDIRECT      = _cfg('SECURE_SSL_REDIRECT', default='False', cast=bool)
    SECURE_HSTS_SECONDS      = _cfg('SECURE_HSTS_SECONDS', default=0, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF    = True
    SECURE_REFERRER_POLICY         = 'same-origin'
    X_FRAME_OPTIONS                = 'DENY'

#  Third-party services 
NOTCHPAY_PUBLIC_KEY   = _cfg("NOTCHPAY_PUBLIC_KEY",   default="")
NOTCHPAY_CALLBACK_URL = _cfg("NOTCHPAY_CALLBACK_URL", default="http://localhost:8000/api/payments/callback/")

AT_USERNAME = _cfg("AT_USERNAME", default="sandbox")
AT_API_KEY  = _cfg("AT_API_KEY",  default="")

CLOUDINARY_CLOUD_NAME = _cfg("CLOUDINARY_CLOUD_NAME", default="")
CLOUDINARY_API_KEY    = _cfg("CLOUDINARY_API_KEY",    default="")
CLOUDINARY_API_SECRET = _cfg("CLOUDINARY_API_SECRET", default="")

EXCHANGE_API_KEY = _cfg("EXCHANGE_API_KEY", default="")

# ── Email 
_email_user = _cfg("EMAIL_HOST_USER", default="")
EMAIL_BACKEND     = (
    "django.core.mail.backends.smtp.EmailBackend"
    if _email_user else
    "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST          = _cfg("EMAIL_HOST",          default="smtp.gmail.com")
EMAIL_PORT          = _cfg("EMAIL_PORT",          default=587, cast=int)
EMAIL_USE_TLS       = _cfg("EMAIL_USE_TLS",       default="True", cast=bool)
EMAIL_HOST_USER     = _email_user
EMAIL_HOST_PASSWORD = _cfg("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL  = _cfg("DEFAULT_FROM_EMAIL",  default="Elite Bank <noreply@elite-bank.cm>")
SERVER_EMAIL        = DEFAULT_FROM_EMAIL
ADMINS              = [("Elite Bank Admin", _email_user)] if _email_user else []

# ── Logging 
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname:8s} {name}: {message}',
            'style':  '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '{levelname}: {message}',
            'style':  '{',
        },
    },
    'handlers': {
        'console': {
            'class':     'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level':    'WARNING',
    },
    'loggers': {
        'django.request': {
            'handlers':  ['console'],
            'level':     'ERROR',
            'propagate': False,
        },
        'accounts': {
            'handlers':  ['console'],
            'level':     'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'transactions': {
            'handlers':  ['console'],
            'level':     'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

#  Jazzmin admin theme 
JAZZMIN_SETTINGS = {
    # Browser tab / admin index
    "site_title":   "Elite Bank Admin",
    "site_header":  "Elite Bank",
    "site_brand":   "Elite Bank",
    "welcome_sign": "Welcome to Elite Bank Administration Panel",
    "copyright":    "© 2026 Elite Bank · Yaoundé, Cameroon",

    # Global search across these models
    "search_model": ["accounts.User", "transactions.Transaction"],

    # Field on User model to use as the avatar in the top-right user menu
    "user_avatar": "avatar_url",

    # Top navigation links
    "topmenu_links": [
        {"name": "Home",     "url": "admin:index",          "permissions": ["auth.view_user"]},
        {"name": "Users",    "url": "admin:accounts_user_changelist"},
        {"name": "Transactions", "url": "admin:transactions_transaction_changelist"},
        {"name": "View App", "url": "http://localhost:4200", "new_window": True},
    ],

    # Sidebar
    "show_sidebar":           True,
    "navigation_expanded":    True,
    "hide_apps":              [],
    "hide_models":            [],
    "order_with_respect_to":  ["accounts", "transactions"],

    # Model icons (Font Awesome 5 classes)
    "icons": {
        "accounts":                          "fas fa-university",
        "accounts.User":                     "fas fa-user-circle",
        "accounts.Beneficiary":              "fas fa-address-book",
        "accounts.Notification":             "fas fa-bell",
        "auth.Group":                        "fas fa-users",
        "transactions":                      "fas fa-money-bill-wave",
        "transactions.Transaction":          "fas fa-exchange-alt",
        "token_blacklist":                   "fas fa-shield-alt",
        "token_blacklist.BlacklistedToken":  "fas fa-ban",
        "token_blacklist.OutstandingToken":  "fas fa-key",
    },
    "default_icon_parents":  "fas fa-folder",
    "default_icon_children": "fas fa-dot-circle",

    # Related-object modal instead of redirect
    "related_modal_active": True,

    # UI options
    "use_google_fonts_cdn": True,
    "show_ui_builder":      False,

    # Form layout
    "changeform_format": "horizontal_tabs",
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text":          False,
    "footer_small_text":          False,
    "body_small_text":            False,
    "brand_small_text":           False,
    "brand_colour":               False,
    "accent":                     "accent-warning",      # gold accent
    "navbar":                     "navbar-dark",
    "no_navbar_border":           True,
    "navbar_fixed":               True,
    "layout_boxed":               False,
    "footer_fixed":               False,
    "sidebar_fixed":              True,
    "sidebar":                    "sidebar-dark-warning", # dark sidebar, gold active
    "sidebar_nav_small_text":     False,
    "sidebar_disable_expand":     False,
    "sidebar_nav_child_indent":   True,
    "sidebar_nav_compact_style":  False,
    "sidebar_nav_legacy_style":   False,
    "sidebar_nav_flat_style":     False,
    "theme":                      "default",
    "dark_mode_theme":            None,
    "button_classes": {
        "primary":   "btn-outline-primary",
        "secondary": "btn-outline-secondary",
        "info":      "btn-outline-info",
        "warning":   "btn-warning",
        "danger":    "btn-danger",
        "success":   "btn-success",
    },
}
