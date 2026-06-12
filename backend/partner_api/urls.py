from django.urls import path

from .views import (
    BookingDetailView,
    BookingListCreateView,
    CategoryListCreateView,
    ManagerDetailView,
    ManagerListCreateView,
    PartnerProfileView,
    ServiceDetailView,
    ServiceKindListCreateView,
    ServiceListCreateView,
    SpecialistDetailView,
    SpecialistListCreateView,
)

urlpatterns = [
    path("profile/", PartnerProfileView.as_view(), name="partner-profile"),
    path("categories/", CategoryListCreateView.as_view(), name="partner-categories"),
    path("service-kinds/", ServiceKindListCreateView.as_view(), name="partner-service-kinds"),
    path("services/", ServiceListCreateView.as_view(), name="partner-services"),
    path("services/<int:service_id>/", ServiceDetailView.as_view(), name="partner-service-detail"),
    path("managers/", ManagerListCreateView.as_view(), name="partner-managers"),
    path("managers/<int:manager_id>/", ManagerDetailView.as_view(), name="partner-manager-detail"),
    path("specialists/", SpecialistListCreateView.as_view(), name="partner-specialists"),
    path("specialists/<int:specialist_id>/", SpecialistDetailView.as_view(), name="partner-specialist-detail"),
    path("bookings/", BookingListCreateView.as_view(), name="partner-bookings"),
    path("bookings/<int:booking_id>/", BookingDetailView.as_view(), name="partner-booking-detail"),
]
