import hashlib
import json
import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from common_api.views import normalize_ru_phone
from partner_api.models import Booking
from .models import CustomerProfile, MobileBookingRecord, MobileNotification


STATUS_GROUPS = {
    "booked": "upcoming", "pending": "upcoming", "записан": "upcoming", "записана": "upcoming",
    "arrived": "in_progress",
    "completed": "completed", "done": "completed", "завершен": "completed", "завершена": "completed",
    "cancelled": "cancelled", "canceled": "cancelled", "отменен": "cancelled", "отменена": "cancelled",
    "no_show": "no_show", "no-show": "no_show", "missed": "no_show", "неявка": "no_show",
}
logger = logging.getLogger(__name__)


def status_group(booking):
    return STATUS_GROUPS.get((booking.status or "").strip().lower(), "unknown")


def booking_revision(booking):
    record = getattr(booking, "mobile_record", None)
    state = [booking.id, booking.starts_at.isoformat(), booking.status, booking.service_name,
             booking.manager_name, str(booking.final_price), booking.pricing_details,
             booking.group_session_id, booking.ends_at.isoformat() if booking.ends_at else None,
             booking.table_id, booking.party_size,
             record.comment if record else "", record.resource_id if record else None,
             record.attendee if record else {}, record.vehicle if record else {}]
    return hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def booking_identity(booking):
    details = booking.pricing_details or []
    entries = [detail for detail in details if isinstance(detail, dict)]
    durations = []
    for detail in entries:
        raw_duration = detail.get("duration_minutes")
        if raw_duration is None:
            continue
        try:
            value = int(raw_duration)
        except (TypeError, ValueError):
            logger.warning("Booking %s has an invalid duration snapshot", booking.id)
            durations = []
            break
        if value <= 0:
            logger.warning("Booking %s has a nonpositive duration snapshot", booking.id)
            durations = []
            break
        durations.append(value)
    duration = sum(durations) if len(durations) == len(entries) else None
    service_ids = [detail["service_id"] for detail in entries if detail.get("service_id")]
    specialist_id = entries[0].get("specialist_id") if entries else None
    if booking.group_session_id:
        specialist_id = booking.group_session.group.specialist_id
    return service_ids, specialist_id, duration or None


def booking_end(booking):
    if booking.ends_at:
        return booking.ends_at
    duration = booking_identity(booking)[2]
    return booking.starts_at + timedelta(minutes=duration) if duration else None


def owned_bookings(customer):
    return Booking.objects.filter(
        tenant_slug="public", partner_profile__isnull=False,
    ).filter(Q(mobile_record__customer=customer) | Q(
        mobile_record__isnull=True, client_phone=customer.phone,
    ))


def claim_unowned_bookings(customer):
    for booking in Booking.objects.filter(tenant_slug="public", client_phone=customer.phone):
        record, _ = MobileBookingRecord.objects.get_or_create(booking=booking)
        if not record.owner_claimed:
            record.customer = customer
            record.owner_claimed = True
            record.save(update_fields=["customer", "owner_claimed"])


def sync_booking_record(booking):
    record, created = MobileBookingRecord.objects.get_or_create(booking=booking)
    customer = CustomerProfile.objects.filter(phone=normalize_ru_phone(booking.client_phone)).first()
    if created:
        record.customer = customer
        record.owner_claimed = bool(customer) or record.owner_claimed or booking.booking_source == Booking.Source.MOBILE
    elif record.customer_id and record.customer.phone != normalize_ru_phone(booking.client_phone):
        record.customer = customer
        record.owner_claimed = bool(customer)
        record.attendee = {}
        record.comment = ""
        record.vehicle = {}
        record.batch_id = None
    state = hashlib.sha256(json.dumps([booking.starts_at.isoformat(), booking.status, booking.manager_name]).encode()).hexdigest()
    if record.customer_id and state != record.notified_state:
        MobileNotification.objects.create(
            customer=record.customer, booking=booking,
            type="booking.created" if not record.notified_state else "booking.changed",
            parameters={"booking_id": booking.id, "starts_at": booking.starts_at.isoformat(), "status": booking.status},
        )
    record.notified_state = state
    record.save()
