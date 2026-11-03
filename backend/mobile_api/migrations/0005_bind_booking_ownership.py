import re
from zoneinfo import ZoneInfo

from django.db import migrations


def bind_bookings(apps, schema_editor):
    Customer = apps.get_model("mobile_api", "CustomerProfile")
    Record = apps.get_model("mobile_api", "MobileBookingRecord")
    Request = apps.get_model("mobile_api", "MobileBookingRequest")
    Booking = apps.get_model("partner_api", "Booking")
    Pass = apps.get_model("partner_api", "BookingPass")
    database = schema_editor.connection.alias
    customers = dict(Customer.objects.using(database).values_list("phone", "id"))
    for booking in Booking.objects.using(database).filter(tenant_slug="public").iterator():
        digits = re.sub(r"\D", "", booking.client_phone)
        if len(digits) == 11 and digits[0] in {"7", "8"}:
            phone = "+7" + digits[1:]
        else:
            phone = "+" + digits
        customer_id = customers.get(phone)
        Record.objects.using(database).get_or_create(
            booking_id=booking.id, defaults={"customer_id": customer_id, "owner_claimed": bool(customer_id) or booking.booking_source == "mobile"},
        )
    local_zone = ZoneInfo("Asia/Almaty")
    for booking_pass in Pass.objects.using(database).all().iterator():
        payload = booking_pass.request_payload
        if payload.get("source") != "mobile":
            continue
        visits = list(Booking.objects.using(database).filter(booking_pass=booking_pass).order_by("visit_number"))
        if not visits:
            continue
        record = Record.objects.using(database).filter(booking=visits[0]).first()
        if not record or not record.customer_id or not payload.get("specialist_id"):
            continue
        canonical = {"partner_id": booking_pass.partner_profile_id, "service_id": booking_pass.service_id,
                     "specialist_id": payload["specialist_id"], "request_id": str(booking_pass.request_id),
                     "starts_at": str(visits[0].starts_at.astimezone(local_zone)),
                     "visits": [str(visit.starts_at.astimezone(local_zone)) for visit in visits]}
        Request.objects.using(database).get_or_create(customer_id=record.customer_id, operation="create",
                                                    request_id=booking_pass.request_id,
                                                    defaults={"payload": canonical, "booking_ids": [visit.id for visit in visits]})


class Migration(migrations.Migration):
    dependencies = [("mobile_api", "0004_mobilecontent_mobilenotification_and_more")]
    operations = [migrations.RunPython(bind_bookings, migrations.RunPython.noop)]
