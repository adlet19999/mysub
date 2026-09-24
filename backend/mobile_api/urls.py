from django.urls import path

from .views import (
    MobileAuthRefreshView,
    MobileAuthRegisterView,
    MobileAuthSendCodeView,
    MobileAuthVerifyCodeView,
    MobileCitiesView,
    MobileCurrentUserAvatarView,
    MobileCurrentUserView,
)


urlpatterns = [
    path("cities/", MobileCitiesView.as_view(), name="mobile-cities"),
    path("auth/send-code/", MobileAuthSendCodeView.as_view(), name="mobile-auth-send-code"),
    path("auth/register/", MobileAuthRegisterView.as_view(), name="mobile-auth-register"),
    path("auth/verify-code/", MobileAuthVerifyCodeView.as_view(), name="mobile-auth-verify-code"),
    path("auth/refresh/", MobileAuthRefreshView.as_view(), name="mobile-auth-refresh"),
    path("users/me/", MobileCurrentUserView.as_view(), name="mobile-current-user"),
    path("users/me/avatar/", MobileCurrentUserAvatarView.as_view(), name="mobile-current-user-avatar"),
]