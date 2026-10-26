from django.db import migrations


def backfill_groups(apps, schema_editor):
	Booking = apps.get_model("partner_api", "Booking")
	BookingGroup = apps.get_model("partner_api", "BookingGroup")
	BookingPass = apps.get_model("partner_api", "BookingPass")
	GroupSession = apps.get_model("partner_api", "GroupSession")
	Service = apps.get_model("partner_api", "Service")
	Specialist = apps.get_model("partner_api", "Specialist")
	db = schema_editor.connection.alias
	groups = {}
	sessions = {}
	for booking in Booking.objects.using(db).filter(partner_profile__isnull=False, group_session__isnull=True, is_individual_override=False).order_by("starts_at", "id").iterator():
		details = booking.pricing_details or []
		if not isinstance(details, list) or (details and (len(details) != 1 or not isinstance(details[0], dict))):
			continue
		detail = details[0] if details else {}
		services = Service.objects.using(db).filter(partner_profile_id=booking.partner_profile_id, tenant_slug=booking.tenant_slug)
		services = services.filter(id=detail["service_id"]) if detail.get("service_id") else services.filter(name=booking.service_name)
		service = services.first() if services.count() == 1 else None
		if not service or detail.get("service_type", service.service_type) != "group":
			continue
		specialist = Specialist.objects.using(db).filter(
			partner_profile_id=booking.partner_profile_id, tenant_slug=booking.tenant_slug,
			full_name__iexact=booking.manager_name or "",
		).first()
		if not specialist:
			continue
		duration = int(detail.get("duration_minutes") or service.duration_minutes)
		key = (booking.partner_profile_id, service.id, specialist.id, duration, booking.booking_pass_id or booking.starts_at)
		session_key = (booking.partner_profile_id, service.id, specialist.id, duration, booking.starts_at)
		session = sessions.get(session_key)
		if session is not None:
			groups.setdefault(key, session.group)
		group = groups.get(key)
		if group is None:
			original_pass = BookingPass.objects.using(db).filter(id=booking.booking_pass_id).first() if booking.booking_pass_id else None
			price_mode = original_pass.price_mode if original_pass else "per_visit"
			group = BookingGroup.objects.using(db).create(
				tenant_slug=booking.tenant_slug, partner_profile_id=booking.partner_profile_id,
				name=service.name, service=service, specialist=specialist,
				capacity=max(1, int(detail.get("max_people") or (service.details or {}).get("max_people") or 1)),
				duration_minutes=duration, price=original_pass.total_price if price_mode == "total" else (booking.base_price if details else service.price or 0),
				price_mode=price_mode,
			)
			groups[key] = group
		if session is None:
			session = GroupSession.objects.using(db).create(group=group, starts_at=booking.starts_at, base_price=booking.base_price if details else group.price)
			sessions[session_key] = session
		Booking.objects.using(db).filter(id=booking.id).update(group_session=session, original_session=session)
		if booking.booking_pass_id:
			BookingPass.objects.using(db).filter(id=booking.booking_pass_id, group__isnull=True).update(group=group)


class Migration(migrations.Migration):
	dependencies = [("partner_api", "0027_independent_groups")]
	operations = [migrations.RunPython(backfill_groups, migrations.RunPython.noop)]
