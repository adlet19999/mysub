from decimal import Decimal

from .models import BookingGroup, GroupSession


def attach_group_session(booking, service, specialist, group=None):
	"""Keep legacy booking clients compatible with independently stored sessions."""
	if service.service_type != "group":
		return None
	session = GroupSession.objects.filter(
		group__partner_profile=booking.partner_profile,
		group__tenant_slug=booking.tenant_slug,
		group__service=service,
		group__specialist=specialist,
		starts_at=booking.starts_at,
		status="scheduled",
	).first()
	if session is None:
		if group is None:
			group = BookingGroup.objects.create(
				tenant_slug=booking.tenant_slug, partner_profile=booking.partner_profile,
				name=service.name, service=service, specialist=specialist,
				capacity=max(1, int((service.details or {}).get("max_people") or 1)),
				duration_minutes=service.duration_minutes,
				price=service.price or Decimal("0.00"),
				price_mode=service.pass_price_mode if service.is_pass else "per_visit",
			)
		session = GroupSession.objects.create(group=group, starts_at=booking.starts_at, original_starts_at=booking.starts_at, base_price=booking.base_price)
	booking.group_session = session
	booking.original_session = session
	booking.save(update_fields=["group_session", "original_session"])
	return session.group
