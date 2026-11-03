from datetime import date, datetime, time, timedelta

from django.utils import timezone
from django.db.models.functions import Lower, Trim
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from common_api.models import BusinessCategory
from partner_api.models import GroupSession, Service, Specialist
from partner_api.intervals import slot_interval, slot_error
from partner_api.restaurant import is_restaurant
from partner_api.views import CLOSED_BOOKING_STATUSES, booking_schedule_error, has_booking_overlap
from .catalog_contract import category_code, booking_category, resource_data, resource_error
from .models import BookingResource, MobileBookingRequest
from .serializers import AvailabilityResponseSerializer, MobileBookingSerializer
from .views import (
    MobileAPIView, MobileAuthenticatedView, MobileCatalogSpecialistAvailabilityView,
    active_catalog_partners, catalog_service_visible, error_response, serialize_mobile_booking,
)
from .booking_contract import owned_bookings


class CategorySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField(allow_null=True)
    allows_group_services = serializers.BooleanField()


class CategoryListSerializer(serializers.Serializer):
    data = CategorySerializer(many=True)
    is_complete = serializers.BooleanField()


class MobileCategoriesView(MobileAPIView):
    @extend_schema(tags=["0. Справочники"], responses={200: CategoryListSerializer})
    def get(self, request):
        return Response({"data": [{"id": item.id, "name": item.name, "code": category_code(item.name),
                                  "allows_group_services": item.allows_group_services}
                                 for item in BusinessCategory.objects.filter(is_archived=False).order_by("name", "id")],
                         "is_complete": True})


class ResourceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    kind = serializers.CharField()
    capacity = serializers.IntegerField()
    service_ids = serializers.ListField(child=serializers.IntegerField())
    booking_period = serializers.CharField()


class ResourceListSerializer(serializers.Serializer):
    data = ResourceSerializer(many=True)
    is_complete = serializers.BooleanField()


class MobileResourcesView(MobileAPIView):
    @extend_schema(tags=["4. Каталог и запись"], responses={200: ResourceListSerializer},
                   parameters=[OpenApiParameter("service_id", int)])
    def get(self, request, partner_id):
        if not active_catalog_partners().filter(id=partner_id).exists():
            return error_response(404, "PARTNER_NOT_FOUND", "Партнёр не найден")
        query = BookingResource.objects.filter(partner_id=partner_id, is_active=True,
                                               services__partner_profile_id=partner_id,
                                               services__tenant_slug="public", services__is_active=True).distinct()
        if request.query_params.get("service_id"):
            try:
                service_id = int(request.query_params["service_id"])
            except ValueError:
                return error_response(400, "VALIDATION_ERROR", "Некорректная услуга", "service_id")
            query = query.filter(services__id=service_id, services__partner_profile_id=partner_id,
                                 services__tenant_slug="public", services__is_active=True)
        return Response({"data": [resource_data(item) for item in query.order_by("id")], "is_complete": True})


class GroupSessionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    group_id = serializers.IntegerField()
    group_name = serializers.CharField()
    service_id = serializers.IntegerField()
    specialist_id = serializers.IntegerField()
    specialist_name = serializers.CharField()
    starts_at = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField()
    capacity = serializers.IntegerField()
    remaining_seats = serializers.IntegerField()
    base_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    is_bookable = serializers.BooleanField()


class GroupSessionListSerializer(serializers.Serializer):
    data = GroupSessionSerializer(many=True)
    is_complete = serializers.BooleanField()


class MobileGroupSessionsView(MobileAPIView):
    @extend_schema(tags=["4. Каталог и запись"], responses={200: GroupSessionListSerializer},
                   parameters=[OpenApiParameter("service_id", int, required=True)])
    def get(self, request, partner_id):
        partner = active_catalog_partners().filter(id=partner_id).first()
        if not partner:
            return error_response(404, "PARTNER_NOT_FOUND", "Партнёр не найден")
        try:
            service_id = int(request.query_params.get("service_id", ""))
        except ValueError:
            return error_response(400, "VALIDATION_ERROR", "Укажите услугу", "service_id")
        service = Service.objects.filter(id=service_id, partner_profile=partner, tenant_slug="public", is_active=True, service_type="group").first()
        if not service or not catalog_service_visible(service):
            return error_response(404, "SERVICE_NOT_FOUND", "Групповая услуга недоступна")
        sessions = GroupSession.objects.filter(group__partner_profile=partner, group__service=service,
                                              group__tenant_slug="public", status="scheduled",
                                              group__specialist__is_active=True,
                                              group__specialist__tenant_slug="public",
                                              group__specialist__capabilities__service=service,
                                              starts_at__gt=timezone.now(),
                                              starts_at__date__lte=timezone.localdate() + timedelta(days=365)).select_related("group__specialist").distinct()
        released = CLOSED_BOOKING_STATUSES - {"completed", "done", "завершен", "завершена"}
        data = []
        for item in sessions.order_by("starts_at", "id"):
            occupied = item.bookings.alias(normalized_status=Lower(Trim("status"))).exclude(normalized_status__in=released).count()
            bookable = (occupied < item.group.capacity and item.group.duration_minutes > 0 and item.base_price >= 0
                        and service.price is not None and service.price >= 0 and service.duration_minutes > 0
                        and slot_error([service], item.starts_at, default=30) is None
                        and booking_schedule_error(item.group.specialist, item.starts_at, item.group.duration_minutes) is None
                        and not has_booking_overlap("public", item.group.specialist.full_name, item.starts_at,
                                                    item.group.duration_minutes, partner_profile=partner, service=service,
                                                    specialist_id=item.group.specialist_id, group_session_id=item.id))
            data.append({"id": item.id, "group_id": item.group_id, "group_name": item.group.name,
                         "service_id": service.id, "specialist_id": item.group.specialist_id,
                         "specialist_name": item.group.specialist.full_name, "starts_at": item.starts_at.isoformat(),
                         "duration_minutes": item.group.duration_minutes, "capacity": item.group.capacity,
                         "remaining_seats": max(0, item.group.capacity - occupied),
                         "base_price": str(item.base_price), "currency": "KZT", "is_bookable": bookable})
        return Response({"data": data, "is_complete": True})


def service_availability(request, partner):
    try:
        requested_date = date.fromisoformat(request.query_params.get("date", ""))
        service_id = int(request.query_params.get("service_id", ""))
    except ValueError:
        return error_response(400, "VALIDATION_ERROR", "Укажите дату и услугу")
    if not timezone.localdate() <= requested_date <= timezone.localdate() + timedelta(days=365):
        return error_response(400, "BOOKING_HORIZON", "Дата должна быть в ближайшие 365 дней")
    service = Service.objects.filter(id=service_id, partner_profile=partner, tenant_slug="public", is_active=True).first()
    if not service or not catalog_service_visible(service):
        return error_response(404, "SERVICE_NOT_FOUND", "Услуга недоступна")
    allocations = {}
    day_start = timezone.make_aware(datetime.combine(requested_date, time.min))
    interval = slot_interval([service], default=30)
    if booking_category(service) in {"photo_studio", "recreation"}:
        try:
            guests = int(request.query_params.get("party_size", "1"))
        except ValueError:
            return error_response(400, "VALIDATION_ERROR", "Количество гостей должно быть числом", "party_size")
        if not 1 <= guests <= 1000:
            return error_response(400, "VALIDATION_ERROR", "Количество гостей должно быть от 1 до 1000", "party_size")
        resources = service.mobile_resources.filter(partner=partner, is_active=True, capacity__gte=guests)
        for resource in resources:
            for minute in range(0, 1440 - service.duration_minutes + 1, interval):
                start = day_start + timedelta(minutes=minute)
                if start > timezone.now() and resource_error(resource, start, service.duration_minutes) is None:
                    key = timezone.localtime(start).strftime("%H:%M")
                    allocation = allocations.setdefault(key, {"starts_at": start.isoformat(), "specialist_ids": [], "resource_ids": []})
                    allocation["resource_ids"].append(resource.id)
    else:
        specialists = Specialist.objects.filter(partner_profile=partner, tenant_slug="public", is_active=True, capabilities__service=service).order_by("id")
        for specialist in specialists:
            result = MobileCatalogSpecialistAvailabilityView().get(request, partner.id, specialist.id)
            if result.status_code != 200:
                return result
            for slot in result.data["slots"]:
                instant = day_start + timedelta(hours=int(slot[:2]), minutes=int(slot[3:]))
                allocation = allocations.setdefault(slot, {"starts_at": instant.isoformat(), "specialist_ids": [], "resource_ids": []})
                allocation["specialist_ids"].append(specialist.id)
    return Response({"date": requested_date.isoformat(), "time_zone": timezone.get_current_timezone_name(),
                     "duration_minutes": service.duration_minutes, "slot_interval_minutes": interval,
                     "slots": sorted(allocations), "allocations": [allocations[key] for key in sorted(allocations)],
                     "is_complete": True})


class MobileBookingRequestView(MobileAuthenticatedView):
    @extend_schema(tags=["4. Каталог и запись"], auth=[{"MobileBearer": []}], responses={200: MobileBookingSerializer, 404: None})
    def get(self, request, request_id):
        receipt = MobileBookingRequest.objects.filter(customer=self.customer, request_id=request_id, operation="create").first()
        if not receipt:
            return error_response(404, "REQUEST_NOT_FOUND", "Запрос не найден")
        booking = owned_bookings(self.customer).filter(id=receipt.booking_ids[0]).first()
        if not booking:
            return error_response(409, "BOOKING_UNAVAILABLE", "Созданная запись больше недоступна")
        return Response(serialize_mobile_booking(booking))


class MobileConfigSerializer(serializers.Serializer):
    currency = serializers.CharField()
    time_zone = serializers.CharField()
    profile_required_fields = serializers.ListField(child=serializers.CharField())
    avatar_max_bytes = serializers.IntegerField()
    max_children = serializers.IntegerField()
    phone_auth = serializers.DictField()
    features = serializers.DictField(child=serializers.BooleanField())


class MobileConfigView(MobileAPIView):
    @extend_schema(tags=["0. Справочники"], responses={200: MobileConfigSerializer})
    def get(self, request):
        from django.conf import settings
        from .push import push_configured
        return Response({"currency": "KZT", "time_zone": timezone.get_current_timezone_name(),
                         "profile_required_fields": ["name", "city_id"], "avatar_max_bytes": 5242880,
                         "max_children": 2,
                         "phone_auth": {"delivery_mode": settings.MOBILE_OTP_MODE,
                                        "code_length": settings.MOBILE_OTP_LENGTH,
                                        "expires_in": settings.MOBILE_OTP_TTL_SECONDS,
                                        "retry_after": settings.MOBILE_OTP_RESEND_SECONDS},
                         "features": {"reviews": True, "favorites": True, "notifications_feed": True,
                                      "push": push_configured(), "checkout": False, "account_deletion_ui_ready": False,
                                      "subscription_readback": True, "deletion_reconciliation": True,
                                      "resource_fixed_duration": True, "resource_nightly_pricing": False,
                                      "district_filter": False, "distance_sort": False}})
