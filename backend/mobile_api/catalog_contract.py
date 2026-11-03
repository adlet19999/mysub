from datetime import timedelta

from django.db.models import Avg, Count
from django.utils import timezone

from partner_api.views import working_schedule_error
from .booking_contract import booking_end, status_group
from .models import BookingReview


def category_code(name):
    value = (name or "").casefold()
    mappings = [
        ("restaurant", ("кафе", "ресторан")), ("beauty", ("красот", "салон")),
        ("medical", ("медицин",)), ("carwash", ("автомой",)),
        ("photo_studio", ("фотостуд", "фото студ")),
        ("recreation", ("курорт", "базы отдыха", "отели", "гостиниц")),
        ("courses", ("кружк", "курс", "образован")),
    ]
    return next((code for code, terms in mappings if any(term in value for term in terms)), None)


def partner_rating(partner):
    data = BookingReview.objects.filter(booking__partner_profile=partner, booking__tenant_slug="public", state="published").aggregate(
        rating=Avg("rating"), rating_count=Count("id"),
    )
    return data


def booking_category(service):
    return category_code(service.category.name) or category_code(service.partner_profile.business_category)


def resource_error(resource, start, duration, exclude_booking_id=None):
    message = working_schedule_error(resource.working_schedule, start, duration)
    if message:
        return message.replace("специалиста", "ресурса")
    end = start + timedelta(minutes=duration)
    records = resource.booking_records.select_related("booking").exclude(booking_id=exclude_booking_id)
    for record in records:
        booking = record.booking
        if status_group(booking) in {"cancelled", "no_show", "completed"}:
            continue
        occupied_end = booking_end(booking)
        if occupied_end is None:
            return "У ресурса есть запись без известной длительности; требуется проверка менеджера"
        if booking.starts_at < end and start < occupied_end:
            return "Ресурс занят"
    return None


def resource_data(resource):
    return {"id": resource.id, "name": resource.name, "kind": resource.kind, "capacity": resource.capacity,
            "service_ids": list(resource.services.filter(is_active=True, tenant_slug="public", partner_profile=resource.partner).order_by("id").values_list("id", flat=True)),
            "booking_period": "fixed_duration"}
