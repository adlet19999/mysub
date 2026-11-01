from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from common_api.models import PartnerProfile
from .intervals import slot_interval
from .models import Booking, BusinessTable, Service
from .restaurant import HOLD, RELEASED, choose_table, is_restaurant, party_size_error, restaurant_action, table_available
from .views import get_partner_profile, partner_allows_group_services, serialize_booking, tenant_from_request, has_client_booking_overlap


def table_data(table):
    return {"id": table.id, "name": table.name, "description": table.description, "capacity": table.capacity, "is_active": table.is_active}


def restaurant_slots(profile, tenant, requested_date, service, party_size, exclude_id=0):
    day = timezone.make_aware(datetime.combine(requested_date, time.min))
    interval = slot_interval([service], default=30)
    now = timezone.now()
    slots = []
    for minute in range(0, 1440, interval):
        start = day + timedelta(minutes=minute)
        if start > now and choose_table(profile, tenant, party_size, start, start + HOLD, (exclude_id,)):
            slots.append(timezone.localtime(start).strftime("%H:%M"))
    return {"date": requested_date.isoformat(), "duration_minutes": 120, "slot_interval_minutes": interval, "time_zone": timezone.get_current_timezone_name(), "slots": slots}


class BookingCapabilitiesView(APIView):
    def get(self, request):
        profile, error = get_partner_profile(request)
        if error is not None:
            return error
        return Response({
            "business_category": profile.business_category,
            "is_restaurant": is_restaurant(profile),
            "allows_group_services": partner_allows_group_services(profile, tenant_from_request(request)),
            "has_individual_passes": Service.objects.filter(partner_profile=profile, tenant_slug=tenant_from_request(request), service_type="individual", is_pass=True).exists(),
        })


class TableListCreateView(APIView):
    def get(self, request):
        profile, error = get_partner_profile(request)
        if error is not None:
            return error
        if not is_restaurant(profile):
            return Response({"message": "Столики доступны только для кафе и ресторанов"}, status=403)
        return Response([table_data(table) for table in BusinessTable.objects.filter(partner_profile=profile, tenant_slug=tenant_from_request(request)).order_by("capacity", "id")])

    @transaction.atomic
    def post(self, request):
        profile, error = get_partner_profile(request)
        if error is not None:
            return error
        profile = PartnerProfile.objects.select_for_update().get(id=profile.id)
        if not is_restaurant(profile):
            return Response({"message": "Столики доступны только для кафе и ресторанов"}, status=403)
        name = str(request.data.get("name") or "").strip()
        capacity = request.data.get("capacity")
        if not name or len(name) > 120 or party_size_error(capacity):
            return Response({"message": "Укажите название столика и целую вместимость от 1 до 1000"}, status=400)
        if BusinessTable.objects.filter(partner_profile=profile, name__iexact=name).exists():
            return Response({"message": "Столик с таким названием уже существует"}, status=409)
        table = BusinessTable.objects.create(partner_profile=profile, tenant_slug=tenant_from_request(request), name=name, capacity=capacity, description=str(request.data.get("description") or "").strip())
        return Response(table_data(table), status=201)


class TableDetailView(APIView):
    @transaction.atomic
    def patch(self, request, table_id):
        profile, error = get_partner_profile(request)
        if error is not None:
            return error
        profile = PartnerProfile.objects.select_for_update().get(id=profile.id)
        if not is_restaurant(profile):
            return Response({"message": "Столики доступны только для кафе и ресторанов"}, status=403)
        table = BusinessTable.objects.filter(id=table_id, partner_profile=profile, tenant_slug=tenant_from_request(request)).first()
        if table is None:
            return Response({"message": "Столик не найден"}, status=404)
        name = str(request.data.get("name", table.name)).strip()
        capacity = request.data.get("capacity", table.capacity)
        active = request.data.get("is_active", table.is_active)
        if not name or len(name) > 120 or party_size_error(capacity) or type(active) is not bool:
            return Response({"message": "Проверьте название, вместимость и активность столика"}, status=400)
        if BusinessTable.objects.filter(partner_profile=profile, name__iexact=name).exclude(id=table.id).exists():
            return Response({"message": "Столик с таким названием уже существует"}, status=409)
        reservations = table.bookings.exclude(status__in=RELEASED).filter(ends_at__gt=timezone.now())
        if table.bookings.filter(status="arrived").exists() and (not active or capacity < table.capacity or name != table.name):
            return Response({"message": "За столиком сидят гости. Сначала завершите обслуживание"}, status=409)
        if (not active and reservations.exists()) or reservations.filter(party_size__gt=capacity).exists():
            return Response({"message": "Столик нужен для действующих броней. Сначала перенесите их"}, status=409)
        table.name, table.capacity, table.is_active = name, capacity, active
        table.description = str(request.data.get("description", table.description)).strip()
        table.save()
        reservations.update(manager_name=name)
        return Response(table_data(table))


class RestaurantBookingActionView(APIView):
    @transaction.atomic
    def patch(self, request, booking_id):
        profile, error = get_partner_profile(request)
        if error is not None:
            return error
        PartnerProfile.objects.select_for_update().get(id=profile.id)
        tenant = tenant_from_request(request)
        booking = Booking.objects.select_for_update().select_related("table", "partner_profile").filter(id=booking_id, partner_profile=profile, tenant_slug=tenant).first()
        if booking is None:
            return Response({"message": "Бронь столика не найдена"}, status=404)
        if not booking.table_id:
            from django.utils.dateparse import parse_datetime
            from .intervals import slot_error
            if not is_restaurant(profile) or request.data.get("action") != "assign_table" or booking.booking_pass_id or booking.group_session_id or booking.status != "booked":
                return Response({"message": "Эту запись нельзя перевести в бронь столика"}, status=409)
            try:
                start = parse_datetime(str(request.data.get("starts_at", "")))
                if start and timezone.is_naive(start):
                    start = timezone.make_aware(start)
                service_id = int(request.data.get("service_id", ""))
            except (TypeError, ValueError):
                start, service_id = None, 0
            service = Service.objects.filter(id=service_id, partner_profile=profile, tenant_slug=tenant, is_active=True, service_type="individual", is_pass=False).first()
            guests = request.data.get("party_size")
            if not start or not service or start <= timezone.now() or party_size_error(guests):
                return Response({"message": "Выберите предложение, будущую дату, время и число гостей"}, status=400)
            message = slot_error([service], start, default=30)
            if message or has_client_booking_overlap(tenant, booking.client_phone, start, 120, exclude_booking_id=booking.id):
                return Response({"message": message or "Клиент уже записан на это время"}, status=409)
            table = choose_table(profile, tenant, guests, start, start + HOLD, (booking.id,))
            if table is None:
                return Response({"message": "Нет свободного столика подходящей вместимости"}, status=409)
            booking.table, booking.party_size = table, guests
            booking.manager_name, booking.starts_at, booking.ends_at = table.name, start, start + HOLD
            booking.service_name = service.name
            booking.pricing_details = [{"service_id": service.id, "service_name": service.name, "duration_minutes": 120, "base_price": str(booking.base_price), "discount_amount": str(booking.discount_amount), "final_price": str(booking.final_price), "discount_percent": 0}]
            booking.save()
            return Response(serialize_booking(booking))
        message = restaurant_action(booking, request.data.get("action"), request.data)
        if message:
            return Response({"message": message}, status=409)
        return Response(serialize_booking(booking))
