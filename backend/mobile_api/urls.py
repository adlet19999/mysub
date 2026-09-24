from django.urls import path

from .views import (
    MobileAuthRefreshView,
    MobileAuthRegisterView,
    MobileAuthSendCodeView,
    MobileAuthVerifyCodeView,
    MobileBookingCancelView,
    MobileBookingsView,
    MobileCatalogPartnersView,
    MobileCatalogPartnerServicesView,
    MobileCatalogPartnerSpecialistsView,
    MobileCatalogServicesView,
    MobileCatalogSpecialistAvailabilityView,
    MobileCitiesView,
    MobileCurrentUserAvatarView,
    MobileCurrentUserView,
)


urlpatterns = [
    path("cities/", MobileCitiesView.as_view(), name="mobile-cities"),
    path("catalog/partners/", MobileCatalogPartnersView.as_view(), name="mobile-catalog-partners"),
    path("catalog/services/", MobileCatalogServicesView.as_view(), name="mobile-catalog-services"),
    path("catalog/partners/<int:partner_id>/services/", MobileCatalogPartnerServicesView.as_view(), name="mobile-catalog-partner-services"),
    path("catalog/partners/<int:partner_id>/specialists/", MobileCatalogPartnerSpecialistsView.as_view(), name="mobile-catalog-partner-specialists"),
    path("catalog/partners/<int:partner_id>/specialists/<int:specialist_id>/availability/", MobileCatalogSpecialistAvailabilityView.as_view(), name="mobile-catalog-specialist-availability"),
    path("bookings/", MobileBookingsView.as_view(), name="mobile-bookings"),
    path("bookings/<int:booking_id>/cancel/", MobileBookingCancelView.as_view(), name="mobile-booking-cancel"),
    path("auth/send-code/", MobileAuthSendCodeView.as_view(), name="mobile-auth-send-code"),
    path("auth/register/", MobileAuthRegisterView.as_view(), name="mobile-auth-register"),
    path("auth/verify-code/", MobileAuthVerifyCodeView.as_view(), name="mobile-auth-verify-code"),
    path("auth/refresh/", MobileAuthRefreshView.as_view(), name="mobile-auth-refresh"),
    path("users/me/", MobileCurrentUserView.as_view(), name="mobile-current-user"),
    path("users/me/avatar/", MobileCurrentUserAvatarView.as_view(), name="mobile-current-user-avatar"),
]