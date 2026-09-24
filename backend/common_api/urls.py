from django.urls import path

from .views import AdminDashboardView, AdminLoginView, AdminPartnerStatusView, AuthForgotPasswordView, AuthInitialPasswordChangeView, AuthLoginView, AuthRegisterView, AuthResetPasswordView, HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="common-health"),
    path("auth/login/", AuthLoginView.as_view(), name="common-auth-login"),
    path("auth/register/", AuthRegisterView.as_view(), name="common-auth-register"),
    path("auth/forgot-password/", AuthForgotPasswordView.as_view(), name="common-auth-forgot-password"),
    path("auth/reset-password/", AuthResetPasswordView.as_view(), name="common-auth-reset-password"),
    path("auth/initial-password-change/", AuthInitialPasswordChangeView.as_view(), name="common-auth-initial-password-change"),
    path("admin/login/", AdminLoginView.as_view(), name="admin-login"),
    path("admin/dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("admin/partners/<int:partner_id>/status/", AdminPartnerStatusView.as_view(), name="admin-partner-status"),
]
