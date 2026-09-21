from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core import views

urlpatterns = [
    # Exempt from tenant resolution (see core/middleware.py EXEMPT_PREFIXES).
    path('health/', views.health, name='health'),
    path('auth/login', TokenObtainPairView.as_view(), name='login'),
    path('auth/refresh', TokenRefreshView.as_view(), name='refresh'),

    # Tenant-scoped: require a valid X-Tenant header.
    path('sync', views.sync, name='sync'),
    path('invoices/', views.list_invoices, name='invoices'),
    path('conflicts/', views.list_conflicts, name='conflicts'),
    path(
        'conflicts/<uuid:conflict_id>/resolve',
        views.resolve_conflict,
        name='resolve-conflict',
    ),
]
