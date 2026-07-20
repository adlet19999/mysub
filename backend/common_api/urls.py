from django.urls import path

from .views import AuthForgotPasswordView, AuthLoginView, AuthRegisterView, AuthResetPasswordView, HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="common-health"),
    path("auth/login/", AuthLoginView.as_view(), name="common-auth-login"),
    path("auth/register/", AuthRegisterView.as_view(), name="common-auth-register"),
    path("auth/forgot-password/", AuthForgotPasswordView.as_view(), name="common-auth-forgot-password"),
    path("auth/reset-password/", AuthResetPasswordView.as_view(), name="common-auth-reset-password"),
]
