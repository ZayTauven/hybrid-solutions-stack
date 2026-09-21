"""Tenant resolution and PostgreSQL session context.

This middleware is what makes row-level security actually do something. The
policies installed by migration 0002 filter on `app.current_tenant_id`; if
nothing sets it, every query returns zero rows (fail-closed). Setting it
wrongly is worse than not setting it at all, so the tenant is verified against
the user's memberships before it ever reaches the database.
"""

import logging

from django.db import connection, transaction
from django.http import JsonResponse

from core.models import Tenant, TenantMembership

logger = logging.getLogger(__name__)

TENANT_HEADER = 'HTTP_X_TENANT'

# Paths that must work before a tenant is known.
EXEMPT_PREFIXES = ('/api/health', '/api/auth/', '/admin/', '/static/')


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(EXEMPT_PREFIXES):
            return self.get_response(request)

        raw_tenant = request.META.get(TENANT_HEADER)
        if not raw_tenant:
            return JsonResponse(
                {'detail': 'X-Tenant header is required.'}, status=400
            )

        if not request.user.is_authenticated:
            # DRF authenticates inside the view, so request.user is still
            # anonymous here for JWT calls. Resolve the token ourselves rather
            # than trusting the header on an unauthenticated request.
            user = _authenticate_jwt(request)
            if user is None:
                return JsonResponse(
                    {'detail': 'Authentication credentials were not provided.'},
                    status=401,
                )
            request.user = user

        tenant = _resolve_tenant(raw_tenant)
        if tenant is None:
            return JsonResponse({'detail': 'Unknown tenant.'}, status=404)

        if not _is_member(request.user, tenant):
            # Deliberately indistinguishable from an unknown tenant: telling a
            # caller that a tenant exists but is not theirs leaks the customer
            # list one probe at a time.
            logger.warning(
                'User %s attempted to act for tenant %s without membership',
                request.user.pk,
                tenant.code,
            )
            return JsonResponse({'detail': 'Unknown tenant.'}, status=404)

        request.tenant = tenant

        # SET LOCAL scopes the setting to this transaction, so it cannot leak
        # to the next request served by the same pooled connection. A plain SET
        # would persist and hand one tenant's context to another's request.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('app.current_tenant_id', %s, true)",
                    [str(tenant.id)],
                )
                cursor.execute(
                    "SELECT set_config('app.client_ip', %s, true)",
                    [_client_ip(request) or ''],
                )
            return self.get_response(request)


def _authenticate_jwt(request):
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

    try:
        result = JWTAuthentication().authenticate(request)
    except (InvalidToken, TokenError):
        return None
    return result[0] if result else None


def _resolve_tenant(raw):
    """Accept either the tenant UUID or its short code."""
    lookup = {'id': raw} if _looks_like_uuid(raw) else {'code': raw}
    return Tenant.objects.filter(**lookup).first()


def _looks_like_uuid(value):
    import uuid

    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _is_member(user, tenant):
    if user.is_superuser:
        return True
    return TenantMembership.objects.filter(user=user, tenant=tenant).exists()


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        # Leftmost entry is the originating client, when a trusted proxy sets it.
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
