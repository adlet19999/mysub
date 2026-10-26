import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView

from common_api.models import PartnerProfile
from common_api.views import PHONE_RU_RE, normalize_ru_phone
from .models import Booking, BookingGroup, BookingPass, GroupSession, Service, Specialist
from .views import (
	CLOSED_BOOKING_STATUSES, MONEY_QUANTUM, active_subscription_phones,
	booking_schedule_error, calculate_booking_pricing, discount_window_for_service,
	get_partner_profile, group_booking_error, has_booking_overlap,
	has_client_booking_overlap, tenant_from_request, to_aware_datetime, to_money,
)


RELEASED_STATUSES = CLOSED_BOOKING_STATUSES - {"completed", "done", "завершен", "завершена"}


def groups_for(profile, tenant):
	return BookingGroup.objects.filter(partner_profile=profile, tenant_slug=tenant).select_related("service", "specialist").prefetch_related("sessions__bookings")


def participant_data(booking):
	return {
		"id": booking.id, "client_name": booking.client_name, "client_phone": booking.client_phone,
		"status": booking.status, "starts_at": timezone.localtime(booking.starts_at).isoformat(),
		"final_price": str(booking.final_price), "base_price": str(booking.base_price),
		"session_id": booking.group_session_id, "original_session_id": booking.original_session_id,
		"is_moved": booking.original_session_id is not None and booking.original_session_id != booking.group_session_id,
		"is_individual_override": booking.is_individual_override,
	}


def session_data(session):
	group = session.group
	bookings = list(session.bookings.all())
	occupied = sum(item.status not in RELEASED_STATUSES for item in bookings)
	return {
		"id": session.id, "group_id": group.id, "group_name": group.name,
		"service_id": group.service_id, "service_name": group.service.name,
		"specialist_id": group.specialist_id, "specialist_name": group.specialist.full_name,
		"starts_at": timezone.localtime(session.starts_at).isoformat(),
		"original_starts_at": timezone.localtime(session.original_starts_at).isoformat() if session.original_starts_at else None,
		"status": session.status, "capacity": group.capacity,
		"occupied_places": occupied, "available_places": max(0, group.capacity - occupied),
		"duration_minutes": group.duration_minutes, "base_price": str(session.base_price),
		"participants": [participant_data(item) for item in bookings],
	}


def group_data(group, detail=False):
	sessions = list(group.sessions.all())
	future = [item for item in sessions if item.status == "scheduled" and item.starts_at >= timezone.now()]
	result = {
		"id": group.id, "name": group.name,
		"service_id": group.service_id, "service_name": group.service.name,
		"specialist_id": group.specialist_id, "specialist_name": group.specialist.full_name,
		"capacity": group.capacity, "duration_minutes": group.duration_minutes,
		"price": str(group.price), "price_mode": group.price_mode,
		"session_count": len(sessions), "future_session_count": len(future),
		"next_session": timezone.localtime(future[0].starts_at).isoformat() if future else None,
		"participant_count": len({booking.client_phone for session in sessions for booking in session.bookings.all() if booking.status not in RELEASED_STATUSES}),
	}
	if detail:
		result["sessions"] = [session_data(item) for item in sessions]
		bookings = Booking.objects.filter(
			Q(group_session__group=group) | Q(original_session__group=group) | Q(booking_pass__group=group),
			partner_profile=group.partner_profile, tenant_slug=group.tenant_slug,
		).distinct().order_by("starts_at", "id")
		result["bookings"] = [participant_data(item) for item in bookings]
	return result


class GroupListCreateView(APIView):
	def get(self, request):
		profile, error = get_partner_profile(request)
		if error is not None:
			return error
		return Response({"items": [group_data(item) for item in groups_for(profile, tenant_from_request(request)).order_by("-created_at")]})

	@transaction.atomic
	def post(self, request):
		profile, error = get_partner_profile(request)
		if error is not None:
			return error
		profile = PartnerProfile.objects.select_for_update().get(id=profile.id)
		tenant = tenant_from_request(request)
		try:
			request_id = uuid.UUID(str(request.data.get("request_id", "")))
			service_id = int(request.data.get("service_id"))
			specialist_id = int(request.data.get("specialist_id"))
			capacity = int(request.data.get("capacity"))
		except (ValueError, TypeError, AttributeError):
			return Response({"message": "Укажите услугу, специалиста, вместимость и request_id"}, status=400)
		name = str(request.data.get("name") or "").strip()
		values = request.data.get("sessions")
		if not name or len(name) > 120 or not isinstance(values, list) or not 1 <= len(values) <= 365:
			return Response({"message": "Укажите название группы и от 1 до 365 дат занятий"}, status=400)
		starts = []
		for value in values:
			try:
				parsed = parse_datetime(value) if isinstance(value, str) else None
			except ValueError:
				parsed = None
			if parsed is None:
				return Response({"message": "Укажите корректные даты занятий в ISO формате"}, status=400)
			starts.append(to_aware_datetime(parsed))
		starts.sort()
		payload = {"tenant": tenant, "name": name, "service_id": service_id, "specialist_id": specialist_id, "capacity": capacity, "sessions": [value.isoformat() for value in starts]}
		previous = groups_for(profile, tenant).filter(request_id=request_id).first()
		if previous:
			if previous.request_payload != payload:
				return Response({"message": "request_id уже использован для другой группы"}, status=409)
			return Response(group_data(previous, detail=True))
		service = Service.objects.filter(id=service_id, tenant_slug=tenant, partner_profile=profile, service_type="group", is_active=True).first()
		specialist = Specialist.objects.filter(id=specialist_id, tenant_slug=tenant, partner_profile=profile, is_active=True, capabilities__service_id=service_id).first()
		if not service or not specialist:
			return Response({"message": "Выберите доступную групповую услугу и её специалиста"}, status=400)
		error = group_booking_error([service])
		if error:
			return Response({"message": error}, status=400)
		if not 1 <= capacity <= min(32767, int((service.details or {}).get("max_people") or 1)):
			return Response({"message": "Вместимость должна быть положительной и не больше лимита услуги"}, status=400)
		if service.is_pass and len(starts) != service.visit_count:
			return Response({"message": f"Для этой услуги нужно занятий: {service.visit_count}"}, status=400)
		for index, starts_at in enumerate(starts):
			error = booking_schedule_error(specialist, starts_at, service.duration_minutes)
			if starts_at < timezone.now():
				error = "Дата занятия уже прошла"
			if index and starts[index - 1] + timedelta(minutes=service.duration_minutes) > starts_at:
				error = "Занятия пересекаются"
			if not error and has_booking_overlap(tenant, specialist.full_name, starts_at, service.duration_minutes, partner_profile=profile):
				error = "Это время уже занято"
			if error:
				return Response({"message": f"{timezone.localtime(starts_at):%d.%m.%Y %H:%M}: {error}"}, status=409)
		price_mode = service.pass_price_mode if service.is_pass else "per_visit"
		price = to_money(service.price)
		group = BookingGroup.objects.create(
			tenant_slug=tenant, partner_profile=profile, name=name, service=service, specialist=specialist,
			capacity=capacity, duration_minutes=service.duration_minutes, price=price,
			price_mode=price_mode, request_id=request_id, request_payload=payload,
		)
		cents, remainder = divmod(int(price * 100), len(starts))
		GroupSession.objects.bulk_create([
			GroupSession(group=group, starts_at=value, original_starts_at=value, base_price=Decimal(cents + (index < remainder)) / 100 if price_mode == "total" else price)
			for index, value in enumerate(starts)
		])
		return Response(group_data(groups_for(profile, tenant).get(id=group.id), detail=True), status=201)


class GroupDetailView(APIView):
	def get(self, request, group_id):
		profile, error = get_partner_profile(request)
		if error is not None:
			return error
		group = groups_for(profile, tenant_from_request(request)).filter(id=group_id).first()
		if not group:
			return Response({"message": "Группа не найдена"}, status=404)
		return Response(group_data(group, detail=True))


class GroupSessionListView(APIView):
	def get(self, request):
		profile, error = get_partner_profile(request)
		if error is not None:
			return error
		sessions = GroupSession.objects.filter(group__partner_profile=profile, group__tenant_slug=tenant_from_request(request)).select_related("group__service", "group__specialist").prefetch_related("bookings")
		return Response({"items": [session_data(item) for item in sessions]})


class GroupEnrollView(APIView):
	@transaction.atomic
	def post(self, request, group_id):
		profile, error = get_partner_profile(request)
		if error is not None:
			return error
		profile = PartnerProfile.objects.select_for_update().get(id=profile.id)
		tenant = tenant_from_request(request)
		group = groups_for(profile, tenant).filter(id=group_id).first()
		if not group:
			return Response({"message": "Группа не найдена"}, status=404)
		try:
			request_id = uuid.UUID(str(request.data.get("request_id", "")))
		except (ValueError, AttributeError):
			return Response({"message": "Укажите корректный request_id"}, status=400)
		name = str(request.data.get("client_name") or "").strip()
		phone = normalize_ru_phone(str(request.data.get("client_phone") or ""))
		ids = request.data.get("session_ids")
		if ids is None:
			ids = [item.id for item in group.sessions.all() if item.status == "scheduled" and item.starts_at >= timezone.now()]
		if not name or len(name) > 120 or not PHONE_RU_RE.fullmatch(phone) or not isinstance(ids, list) or not ids or any(type(value) is not int for value in ids) or len(set(ids)) != len(ids):
			return Response({"message": "Укажите имя, полный телефон и неповторяющиеся даты занятий"}, status=400)
		payload = {"tenant": tenant, "group_id": group.id, "client_name": name, "client_phone": phone, "session_ids": sorted(ids)}
		previous = BookingPass.objects.filter(partner_profile=profile, request_id=request_id).first()
		if previous:
			if previous.request_payload != payload:
				return Response({"message": "request_id уже использован для другой записи"}, status=409)
			return Response(group_data(groups_for(profile, tenant).get(id=group.id), detail=True))
		sessions = [item for item in group.sessions.all() if item.id in ids]
		if len(sessions) != len(ids):
			return Response({"message": "Выбранное занятие не относится к этой группе"}, status=400)
		if not group.service.is_active or not group.specialist.is_active:
			return Response({"message": "Услуга или специалист больше недоступны"}, status=409)
		for session in sessions:
			error = booking_schedule_error(group.specialist, session.starts_at, group.duration_minutes)
			if session.status != "scheduled" or session.starts_at < timezone.now():
				error = "Занятие отменено или уже прошло"
			if session_data(session)["available_places"] <= 0:
				error = "На занятии больше нет мест"
			if has_client_booking_overlap(tenant, phone, session.starts_at, group.duration_minutes, partner_profile=profile):
				error = "Клиент уже записан на пересекающееся время"
			if error:
				return Response({"message": f"{timezone.localtime(session.starts_at):%d.%m.%Y %H:%M}: {error}"}, status=409)
		enrollment = BookingPass.objects.create(
			partner_profile=profile, group=group, request_id=request_id, request_payload=payload,
			service=group.service, visit_count=len(sessions), price_mode=group.price_mode,
			total_price=sum((item.base_price for item in sessions), Decimal("0.00")),
		)
		for index, session in enumerate(sessions):
			pricing = calculate_booking_pricing([group.service], group.specialist, session.starts_at, client_phone=phone, allow_discount=False)
			pricing.update(base_price=session.base_price, discount_amount=Decimal("0.00"), final_price=session.base_price)
			pricing["pricing_details"][0].update(
				base_price=str(session.base_price), final_price=str(session.base_price),
				duration_minutes=group.duration_minutes, max_people=group.capacity, service_type="group",
			)
			Booking.objects.create(
				tenant_slug=tenant, partner_profile=profile, booking_pass=enrollment, visit_number=index + 1,
				group_session=session, original_session=session, service_name=group.service.name,
				manager_name=group.specialist.full_name, starts_at=session.starts_at,
				client_name=name, client_phone=phone, booking_source=Booking.Source.MANUAL, **pricing,
			)
		return Response(group_data(groups_for(profile, tenant).get(id=group.id), detail=True), status=201)


def refresh_visit_pricing(booking, service, specialist, starts_at, duration):
	window = discount_window_for_service(specialist, starts_at, 0, duration)
	eligible = booking.booking_source == Booking.Source.MOBILE and bool(window) and booking.client_phone in active_subscription_phones([booking.client_phone], starts_at)
	percent = service.discount_percent if eligible else 0
	discount = (booking.base_price * Decimal(percent) / 100).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
	booking.discount_amount, booking.final_price = discount, booking.base_price - discount
	detail = dict(booking.pricing_details[0]) if booking.pricing_details else {
		"service_id": service.id, "service_name": booking.service_name, "service_type": "group",
		"duration_minutes": duration, "max_people": booking.original_session.group.capacity,
		"base_price": str(booking.base_price),
	}
	detail.update(discount_percent=percent, discount_amount=str(discount), final_price=str(booking.final_price), discount_window=window)
	booking.pricing_details = [detail]


class GroupSessionDetailView(APIView):
	@transaction.atomic
	def patch(self, request, session_id):
		profile, error = get_partner_profile(request)
		if error is not None:
			return error
		profile = PartnerProfile.objects.select_for_update().get(id=profile.id)
		tenant = tenant_from_request(request)
		session = GroupSession.objects.filter(id=session_id, group__partner_profile=profile, group__tenant_slug=tenant).select_related("group__service", "group__specialist").prefetch_related("bookings").first()
		if not session:
			return Response({"message": "Занятие не найдено"}, status=404)
		action = request.data.get("action")
		if action not in {"cancel", "move"}:
			return Response({"message": "Выберите отмену или разовый перенос занятия"}, status=400)
		if session.status == "cancelled":
			if action == "cancel":
				return Response(session_data(session))
			return Response({"message": "Отменённое занятие нельзя перенести"}, status=409)
		bookings = list(session.bookings.all())
		if session.starts_at < timezone.now() or any(item.status in {"completed", "done", "завершен", "завершена", "no_show", "no-show", "missed", "неявка"} for item in bookings):
			return Response({"message": "Нельзя менять прошедшее занятие или занятие с отмеченной явкой"}, status=409)
		active = [item for item in bookings if item.status not in CLOSED_BOOKING_STATUSES]
		if action == "cancel":
			Booking.objects.filter(id__in=[item.id for item in active]).update(status="cancelled")
			session.status = "cancelled"
			session.save(update_fields=["status"])
		else:
			try:
				parsed = parse_datetime(str(request.data.get("starts_at", "")))
			except ValueError:
				parsed = None
			if parsed is None:
				return Response({"message": "Выберите корректные дату и время занятия"}, status=400)
			starts_at = to_aware_datetime(parsed)
			group = session.group
			if not group.specialist.is_active or not group.service.is_active:
				return Response({"message": "Услуга или специалист недоступны"}, status=409)
			error = booking_schedule_error(group.specialist, starts_at, group.duration_minutes)
			if starts_at < timezone.now():
				error = "Нельзя перенести занятие в прошлое"
			if has_booking_overlap(tenant, group.specialist.full_name, starts_at, group.duration_minutes, partner_profile=profile, exclude_session_id=session.id):
				error = "Новое время занято у специалиста"
			if GroupSession.objects.filter(group=group, starts_at=starts_at).exclude(id=session.id).exists():
				error = "В этой группе уже есть занятие на выбранное время"
			if error:
				return Response({"message": error}, status=409)
			for booking in active:
				if has_client_booking_overlap(tenant, booking.client_phone, starts_at, group.duration_minutes, partner_profile=profile if booking.booking_source != Booking.Source.MOBILE else None, exclude_booking_id=booking.id):
					return Response({"message": f"{booking.client_name}: на новом времени есть другая запись. Занятие не перенесено."}, status=409)
			session.original_starts_at = session.original_starts_at or session.starts_at
			session.starts_at = starts_at
			session.save(update_fields=["starts_at", "original_starts_at"])
			for booking in active:
				refresh_visit_pricing(booking, group.service, group.specialist, starts_at, group.duration_minutes)
				booking.starts_at = starts_at
				booking.save(update_fields=["starts_at", "discount_amount", "final_price", "pricing_details"])
		session = GroupSession.objects.select_related("group__service", "group__specialist").prefetch_related("bookings").get(id=session.id)
		return Response(session_data(session))


class GroupParticipantView(APIView):
	@transaction.atomic
	def patch(self, request, booking_id):
		profile, error = get_partner_profile(request)
		if error is not None:
			return error
		profile = PartnerProfile.objects.select_for_update().get(id=profile.id)
		tenant = tenant_from_request(request)
		booking = Booking.objects.filter(id=booking_id, partner_profile=profile, tenant_slug=tenant, original_session__isnull=False).select_related("original_session__group__service").first()
		if not booking:
			return Response({"message": "Запись участника не найдена"}, status=404)
		action = request.data.get("action")
		if action not in {"cancel", "complete", "no_show", "move"}:
			return Response({"message": "Неизвестное действие с участником"}, status=400)
		if booking.status == {"cancel": "cancelled", "complete": "completed", "no_show": "no_show"}.get(action):
			return Response(participant_data(booking))
		if booking.status in CLOSED_BOOKING_STATUSES:
			return Response({"message": "Это посещение уже завершено или отменено"}, status=409)
		if action != "move":
			booking.status = {"cancel": "cancelled", "complete": "completed", "no_show": "no_show"}[action]
			booking.save(update_fields=["status"])
			return Response(participant_data(booking))
		service = booking.original_session.group.service
		duration = booking.original_session.group.duration_minutes
		target = None
		if "session_id" in request.data:
			if type(request.data["session_id"]) is not int:
				return Response({"message": "Выберите занятие для переноса"}, status=400)
			target = GroupSession.objects.filter(
				id=request.data["session_id"], group__partner_profile=profile, group__tenant_slug=tenant,
				group__service=service, group__duration_minutes=duration, status="scheduled",
			).select_related("group__specialist", "group__service").prefetch_related("bookings").first()
			if not target:
				return Response({"message": "Выберите доступное занятие той же услуги и длительности"}, status=400)
			if target.id == booking.group_session_id:
				return Response({"message": "Клиент уже записан на это занятие"}, status=400)
			if session_data(target)["available_places"] <= 0:
				return Response({"message": "На выбранном занятии больше нет мест"}, status=409)
			specialist, starts_at = target.group.specialist, target.starts_at
		else:
			try:
				parsed = parse_datetime(str(request.data.get("starts_at", "")))
			except ValueError:
				parsed = None
			specialist_id = request.data.get("specialist_id")
			if parsed is None or type(specialist_id) is not int:
				return Response({"message": "Выберите специалиста и корректное время переноса"}, status=400)
			starts_at = to_aware_datetime(parsed)
			specialist = Specialist.objects.filter(id=specialist_id, partner_profile=profile, tenant_slug=tenant, is_active=True, capabilities__service=service).first()
		if not specialist or not specialist.is_active or not service.is_active:
			return Response({"message": "Услуга или специалист недоступны"}, status=409)
		error = booking_schedule_error(specialist, starts_at, duration)
		if starts_at < timezone.now():
			error = "Нельзя перенести посещение в прошлое"
		if not target and has_booking_overlap(tenant, specialist.full_name, starts_at, duration, partner_profile=profile, exclude_booking_id=booking.id):
			error = "Это время занято, в том числе пустым занятием группы"
		if has_client_booking_overlap(tenant, booking.client_phone, starts_at, duration, partner_profile=profile if booking.booking_source != Booking.Source.MOBILE else None, exclude_booking_id=booking.id):
			error = "Клиент уже записан на пересекающееся время"
		if error:
			return Response({"message": error}, status=409)
		refresh_visit_pricing(booking, service, specialist, starts_at, duration)
		booking.starts_at, booking.manager_name = starts_at, specialist.full_name
		booking.group_session, booking.is_individual_override = target, target is None
		booking.save()
		return Response(participant_data(booking))
