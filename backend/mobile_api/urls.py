from django.urls import path

from .views import (
    MobileAuthRefreshView,
    MobileAuthRegisterView,
    MobileAuthSendCodeView,
    MobileAuthVerifyCodeView,
    MobileCitiesView,
    MobileChildDetailView,
    MobileChildrenView,
    MobileCurrentUserView,
)


urlpatterns = [
    path("cities/", MobileCitiesView.as_view(), name="mobile-cities"),
    path("auth/send-code/", MobileAuthSendCodeView.as_view(), name="mobile-auth-send-code"),
    path("auth/register/", MobileAuthRegisterView.as_view(), name="mobile-auth-register"),
    path("auth/verify-code/", MobileAuthVerifyCodeView.as_view(), name="mobile-auth-verify-code"),
    path("auth/refresh/", MobileAuthRefreshView.as_view(), name="mobile-auth-refresh"),
    path("users/me/", MobileCurrentUserView.as_view(), name="mobile-current-user"),
    path("users/me/children/", MobileChildrenView.as_view(), name="mobile-children"),
    path("users/me/children/<int:child_id>/", MobileChildDetailView.as_view(), name="mobile-child-detail"),
]