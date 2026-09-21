"""Django settings for the hybrid stack backend."""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'core',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Must run after authentication: it needs request.user to verify that the
    # caller is actually a member of the tenant it claims in X-Tenant.
    'core.middleware.TenantContextMiddleware',
]

ROOT_URLCONF = 'myapp.urls'

TEMPLATES = [
    {
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
    },
]

WSGI_APPLICATION = 'myapp.wsgi.application'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# DATABASE_URL must point at the hybrid_app role, never at the superuser:
# a superuser bypasses every RLS policy (see postgresql-schema/01-init-roles.sh).
DATABASES = {
    'default': dj_database_url.parse(
        os.environ.get(
            'DATABASE_URL',
            'postgresql://hybrid_app:changeme_app@postgres:5432/shared_meta',
        ),
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# REST framework & JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
}

# A long access token is deliberate, not an oversight: a field device may stay
# offline for a full working day and must keep authenticating locally. The
# trade-off is that revocation is slow, so keep the lifetime as short as the
# deployment's connectivity actually allows.
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(
        seconds=int(os.environ.get('JWT_ACCESS_TOKEN_LIFETIME', 86400))
    ),
    'REFRESH_TOKEN_LIFETIME': timedelta(
        seconds=int(os.environ.get('JWT_REFRESH_TOKEN_LIFETIME', 604800))
    ),
    'SIGNING_KEY': os.environ.get('JWT_SECRET_KEY', SECRET_KEY),
}

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        'CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000'
    ).split(',')
    if o.strip()
]
# X-Tenant is a custom header: without it here, the browser's preflight fails
# and every sync call is blocked before it reaches Django.
CORS_ALLOW_HEADERS = [
    'accept',
    'authorization',
    'content-type',
    'origin',
    'user-agent',
    'x-tenant',
]

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', REDIS_URL)
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = 'UTC'

CELERY_BEAT_SCHEDULE = {
    'purge-synced-events': {
        'task': 'core.tasks.purge_synced_events',
        'schedule': 24 * 60 * 60,
    },
}

# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------
SYNC_AUTO_PURGE_SYNCED_AFTER_DAYS = int(
    os.environ.get('SYNC_AUTO_PURGE_SYNCED_AFTER_DAYS', 90)
)

# Events returned per sync call before the response is truncated.
SYNC_BATCH_SIZE = int(os.environ.get('SYNC_BATCH_SIZE', 500))

# Per-entity conflict strategy. See skills/conflict-resolution/SKILL.md.
# The default is 'manual' on purpose: guessing wrong on money is worse than
# asking a human.
CONFLICT_RESOLUTION = {
    'invoice': 'manual',
    'contact': 'field-merge',
    'note': 'lww',
    'default': 'manual',
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': os.environ.get('LOG_LEVEL', 'INFO')},
}
