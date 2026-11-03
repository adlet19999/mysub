from datetime import timedelta
from decimal import Decimal, InvalidOperation
import logging

from django.db import transaction
from django.utils import timezone

from common_api.models import PartnerProfile
from .intervals import slot_error
from .models import Booking, BookingExtension, BusinessTable, Service


logger = logging.getLogger(__name__)
HOLD = timedelta(hours=2)
RELEASED = {"cancelled", "canceled", "no_show", "no-show", "missed", "completed", "done"}


def is_restaurant(profile):
    return profile.business_category == "Кафе и рестораны"


def restaurant_booking_data(booking):
    if not booking.table_id:
        return None
    end = booking.ends_at
    initial_end = min(booking.starts_at + HOLD, end) if end else booking.starts_at + HOLD
    segments = [{"starts_at": timezone.localtime(booking.starts_at).isoformat(), "ends_at": timezone.localtime(initial_end).isoformat(), "is_extension": False}]
    for extension in booking.extensions.all():
        if end and extension.starts_at >= end:
            continue
        segments.append({"starts_at": timezone.localtime(extension.starts_at).isoformat(), "ends_at": timezone.localtime(min(extension.ends_at, end) if end else extension.ends_at).isoformat(), "is_extension": True})
    return {
        "table_id": booking.table_id, "table_name": booking.table.name,
        "table_capacity": booking.table.capacity, "party_size": booking.party_size,
        "ends_at": timezone.localtime(end).isoformat() if end else None,
        "arrived_at": booking.arrived_at.isoformat() if booking.arrived_at else None,
        "completed_at": booking.completed_at.isoformat() if booking.completed_at else None,
        "paid_amount": str(booking.paid_amount) if booking.paid_amount is not None else None,
        "notice": booking.table_notice, "segments": segments,
    }


def party_size_error(value):
    if type(value) is not int or not 1 <= value <= 1000:
        return "Количество гостей должно быть целым числом от 1 до 1000"
    return None


def table_available(table, starts_at, ends_at, exclude_ids=()):
    bookings = table.bookings.exclude(id__in=exclude_ids).exclude(status__in=RELEASED)
    now = timezone.now()
    for booking in bookings:
        occupied_end = booking.ends_at or booking.starts_at + HOLD
        if booking.status == "arrived":
            while occupied_end <= now:
                occupied_end += HOLD
        if booking.starts_at < ends_at and starts_at < occupied_end:
            return False
    return True


def choose_table(profile, tenant, party_size, starts_at, ends_at, exclude_ids=(), exclude_table_id=None):
    tables = BusinessTable.objects.filter(partner_profile=profile, tenant_slug=tenant, is_active=True, capacity__gte=party_size).exclude(id=exclude_table_id).order_by("capacity", "id")
    return next((table for table in tables if table_available(table, starts_at, ends_at, exclude_ids)), None)


def create_restaurant_booking(*, profile, tenant, service, starts_at, party_size, client_name, client_phone, source):
    from .views import calculate_booking_pricing, has_client_booking_overlap

    if not is_restaurant(profile) or not service.is_active or service.partner_profile_id != profile.id or service.tenant_slug != tenant or service.service_type != "individual" or service.is_pass:
        return None, "Предложение недоступно для бронирования столика"
    message = party_size_error(party_size) or slot_error([service], starts_at, default=30)
    if message:
        return None, message
    if starts_at <= timezone.now():
        return None, "Нельзя забронировать прошедшее время"
    if has_client_booking_overlap(tenant, client_phone, starts_at, 120):
        return None, "У клиента уже есть пересекающаяся запись"
    table = choose_table(profile, tenant, party_size, starts_at, starts_at + HOLD)
    if table is None:
        return None, "Нет свободного столика подходящей вместимости на выбранные два часа"
    pricing = calculate_booking_pricing([service], None, starts_at, client_phone=client_phone, allow_discount=source == Booking.Source.MOBILE)
    pricing["pricing_details"][0]["duration_minutes"] = 120
    booking = Booking.objects.create(
        tenant_slug=tenant, partner_profile=profile, service_name=service.name,
        manager_name=table.name, table=table, party_size=party_size,
        starts_at=starts_at, ends_at=starts_at + HOLD, client_name=client_name,
        client_phone=client_phone, status="booked", booking_source=source, **pricing,
    )
    return booking, None


def renew_locked_booking(booking, now):
    if booking.status != "arrived" or not booking.ends_at or booking.ends_at > now:
        return False
    previous_end = booking.ends_at
    new_end = previous_end
    while new_end <= now:
        new_end += HOLD
    conflicts = booking.table.bookings.exclude(id=booking.id).exclude(status__in=RELEASED).filter(starts_at__lt=new_end, ends_at__gt=previous_end).order_by("starts_at", "id")
    unresolved = []
    for other in conflicts:
        replacement = None
        if other.status == "booked" and other.starts_at >= now:
            replacement = choose_table(booking.partner_profile, booking.tenant_slug, other.party_size, other.starts_at, other.ends_at, exclude_ids=(other.id,), exclude_table_id=booking.table_id)
        if replacement:
            previous_name = other.table.name
            other.table = replacement
            other.manager_name = replacement.name
            other.table_notice = f"Столик автоматически изменён: {previous_name} → {replacement.name}. Предыдущие гости продолжают обслуживание."
            other.save(update_fields=["table", "manager_name", "table_notice"])
        else:
            unresolved.append(other.id)
            other.table_notice = f"Конфликт посадки: предыдущие гости ещё занимают {booking.table.name}. Требуется решение менеджера."
            other.save(update_fields=["table_notice"])
    cursor = previous_end
    while cursor < new_end:
        BookingExtension.objects.get_or_create(booking=booking, starts_at=cursor, defaults={"ends_at": cursor + HOLD})
        cursor += HOLD
    booking.ends_at = new_end
    booking.table_notice = f"Гости продолжают обслуживание. Конфликт с бронями: {', '.join(map(str, unresolved))}. Назначьте другой столик или согласуйте время." if unresolved else ""
    booking.save(update_fields=["ends_at", "table_notice"])
    if unresolved:
        logger.warning("Restaurant renewal conflict: booking=%s conflicting_bookings=%s", booking.id, unresolved)
    return True


def renew_restaurant_bookings(now=None):
    now = now or timezone.now()
    ids = list(Booking.objects.filter(table__isnull=False, status="arrived", ends_at__lte=now).values_list("id", "partner_profile_id"))
    renewed = 0
    for booking_id, profile_id in ids:
        with transaction.atomic():
            PartnerProfile.objects.select_for_update().get(id=profile_id)
            booking = Booking.objects.select_for_update(of=("self",)).select_related("table", "partner_profile").get(id=booking_id)
            renewed += int(renew_locked_booking(booking, now))
    return renewed


def restaurant_action(booking, action, payload):
    now = timezone.now()
    if action == "arrive":
        if booking.status == "arrived":
            return None
        if booking.status != "booked" or booking.starts_at > now:
            return "Приход можно отметить только для начавшейся активной брони"
        arrival_end = booking.ends_at
        while arrival_end <= now:
            arrival_end += HOLD
        if not table_available(booking.table, now, arrival_end, (booking.id,)):
            return "Столик занят другими гостями. Сначала перенесите бронь на свободный столик"
        booking.status = "arrived"
        booking.arrived_at = now
        booking.save(update_fields=["status", "arrived_at"])
        renew_locked_booking(booking, now)
    elif action == "finish":
        try:
            amount = Decimal(str(payload.get("paid_amount", "")))
            if not amount.is_finite() or amount < 0 or amount >= Decimal("10000000000") or amount != amount.quantize(Decimal("0.01")):
                return "Укажите полученную оплату: неотрицательная сумма с точностью до копеек"
        except (InvalidOperation, ValueError):
            return "Укажите полученную оплату"
        if booking.status == "completed":
            return None if booking.paid_amount == amount else "Визит уже завершён с другой суммой оплаты"
        if booking.status != "arrived":
            return "Завершить обслуживание можно только после подтверждения прихода"
        booking.status = "completed"
        booking.completed_at = now
        booking.paid_amount = amount
        booking.ends_at = max(booking.starts_at + timedelta(minutes=1), now)
        booking.table_notice = ""
        booking.save(update_fields=["status", "completed_at", "paid_amount", "ends_at", "table_notice"])
    elif action in {"cancel", "no_show"}:
        target = "cancelled" if action == "cancel" else "no_show"
        if booking.status == target:
            return None
        if booking.status != "booked":
            return "Посадка уже подтверждена или визит закрыт. Для сидящих гостей завершите обслуживание с оплатой"
        booking.status = target
        booking.table_notice = ""
        booking.save(update_fields=["status", "table_notice"])
    elif action == "move":
        from django.utils.dateparse import parse_datetime
        try:
            starts_at = parse_datetime(str(payload.get("starts_at", "")))
            if starts_at and timezone.is_naive(starts_at):
                starts_at = timezone.make_aware(starts_at)
        except ValueError:
            starts_at = None
        if booking.status != "booked" or not starts_at or starts_at <= now:
            return "Перенести можно только активную бронь на будущее время"
        party_size = payload.get("party_size", booking.party_size)
        if party_size_error(party_size):
            return party_size_error(party_size)
        service_ids = [detail["service_id"] for detail in booking.pricing_details]
        services = list(Service.objects.filter(id__in=service_ids))
        message = slot_error(services, starts_at, default=30)
        if message:
            return message
        from .views import has_client_booking_overlap
        if has_client_booking_overlap(booking.tenant_slug, booking.client_phone, starts_at, 120, exclude_booking_id=booking.id):
            return "У клиента уже есть пересекающаяся запись"
        table = choose_table(booking.partner_profile, booking.tenant_slug, party_size, starts_at, starts_at + HOLD, (booking.id,))
        if table is None:
            return "Нет свободного столика подходящей вместимости"
        booking.table = table
        booking.manager_name = table.name
        booking.party_size = party_size
        booking.starts_at = starts_at
        booking.ends_at = starts_at + HOLD
        booking.table_notice = ""
        booking.save(update_fields=["table", "manager_name", "party_size", "starts_at", "ends_at", "table_notice"])
    else:
        return "Неизвестное действие с ресторанной бронью"
    return None
