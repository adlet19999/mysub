from django.urls import path

from .views import AuthLoginView, AuthRegisterView, HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="common-health"),
    path("auth/login/", AuthLoginView.as_view(), name="common-auth-login"),
    path("auth/register/", AuthRegisterView.as_view(), name="common-auth-register"),
]
