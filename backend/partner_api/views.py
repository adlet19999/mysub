import base64
import binascii
import re
import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from django.contrib.auth.models import User
from django.db.models import Q
from django.conf import settings
from django.http import FileResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.response import Response
from rest_framework.views import APIView

from common_api.models import PartnerProfile
from common_api.views import normalize_ru_phone, PHONE_RU_RE

from .models import Booking, Category, Manager, Service, ServiceKind, Specialist, SpecialistService


def tenant_from_request(request) -> str:
	return (request.headers.get("X-Tenant") or "public").strip() or "public"


def partner_category_from_request(request) -> str:
	return (request.headers.get("X-Partner-Category") or "").strip()


def partner_email_from_request(request) -> str:
	return (request.headers.get("X-Partner-Email") or "").strip().lower()


def request_actor_role(request) -> str:
	email = partner_email_from_request(request)
	if not email:
		return ""
	profile = (
		PartnerProfile.objects.select_related("user")
		.filter(Q(user__username__iexact=email) | Q(user__email__iexact=email))
		.first()
	)
	if not profile:
		return ""
	return (profile.user_type or "").strip().lower()


def manager_partner_profile_from_request(request):
	email = partner_email_from_request(request)
	if not email:
		return None
	tenant = tenant_from_request(request)
	manager_item = (
		Manager.objects.select_related("partner_profile")
		.filter(tenant_slug=tenant, email__iexact=email, is_active=True)
		.first()
	)
	if not manager_item:
		return None
	return manager_item.partner_profile


def get_partner_profile(request):
	email = partner_email_from_request(request)
	if not email:
		return None, Response({"message": "X-Partner-Email обязателен"}, status=401)
	profile = (
		PartnerProfile.objects.select_related("user")
		.filter(Q(user__username__iexact=email) | Q(user__email__iexact=email), user_type="partner")
		.first()
	)
	if not profile:
		profile = manager_partner_profile_from_request(request)
	if not profile:
		return None, Response({"message": "Партнер не найден"}, status=401)
	return profile, None


def parse_bool(value, default: bool) -> bool:
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	raw = str(value).strip().lower()
	if raw in {"1", "true", "yes", "on"}:
		return True
	if raw in {"0", "false", "no", "off"}:
		return False
	return default


def parse_positive_int(value, field_name: str):
	if value is None or str(value).strip() == "":
		return None, None
	try:
		parsed = int(value)
	except (TypeError, ValueError):
		return None, f"{field_name} должен быть числом"
	if parsed <= 0:
		return None, f"{field_name} должен быть больше 0"
	return parsed, None


def normalize_service_image_url(value: str) -> str:
	url = str(value or "").strip()
	if not url:
		return ""
	prefix = "/api/v1/partner/service-images/"
	if url.startswith(prefix) and url.endswith("/"):
		file_part = url[len(prefix) : -1]
		if file_part and "/" not in file_part:
			return f"{prefix}{file_part}"
	return url


def normalize_profile_image_url(value: str) -> str:
	url = str(value or "").strip()
	prefix = "/api/v1/partner/profile-images/"
	if url.startswith(prefix) and url.endswith("/"):
		file_part = url[len(prefix) : -1]
		if file_part and "/" not in file_part:
			return f"{prefix}{file_part}"
	return url


def compress_image_base64(image_base64: str):
	raw = str(image_base64 or "").strip()
	if not raw:
		return "", None
	if not raw.lower().startswith("data:image/"):
		return "", "Некорректный формат изображения"

	parts = raw.split(",", 1)
	if len(parts) != 2 or ";base64" not in parts[0].lower():
		return "", "Некорректный формат изображения"

	payload = re.sub(r"\s+", "", parts[1])
	if not payload:
		return "", "Некорректные base64-данные изображения"
	payload += "=" * ((-len(payload)) % 4)

	try:
		binary = base64.b64decode(payload, validate=False)
	except (binascii.Error, ValueError):
		return "", "Некорректные base64-данные изображения"

	if len(binary) > 5 * 1024 * 1024:
		return "", "Изображение слишком большое (максимум 5MB)"

	try:
		with Image.open(BytesIO(binary)) as source:
			if source.width * source.height > 25_000_000:
				return "", "Разрешение изображения слишком большое"
			image = ImageOps.exif_transpose(source)
			image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
			if image.mode not in {"RGB", "RGBA"}:
				image = image.convert("RGBA")
			if image.mode == "RGBA":
				background = Image.new("RGB", image.size, "white")
				background.paste(image, mask=image.getchannel("A"))
				image = background
			else:
				image = image.convert("RGB")
			output = BytesIO()
			image.save(output, format="WEBP", quality=78, method=6)
	except (OSError, UnidentifiedImageError, ValueError):
		return "", "Не удалось обработать изображение"

	return f"data:image/webp;base64,{base64.b64encode(output.getvalue()).decode('ascii')}", None


def save_profile_image_from_base64(image_base64: str, tenant: str, partner_profile_id: int, image_type: str):
	raw, compression_error = compress_image_base64(image_base64)
	if compression_error:
		return "", compression_error
	if not raw:
		return "", None

	payload = raw.split(",", 1)[1]
	try:
		binary = base64.b64decode(payload, validate=False)
	except (binascii.Error, ValueError):
		return "", "Некорректные base64-данные изображения"

	profile_images_dir = Path(settings.MEDIA_ROOT) / "profile_images"
	profile_images_dir.mkdir(parents=True, exist_ok=True)
	file_name = f"{image_type}-tenant-{tenant}-partner-{partner_profile_id}-{uuid.uuid4().hex}.webp"
	(profile_images_dir / file_name).write_bytes(binary)
	return f"/api/v1/partner/profile-images/{file_name}", None


def save_service_image_from_base64(image_base64: str, tenant: str, partner_profile_id: int):
	raw, compression_error = compress_image_base64(image_base64)
	if compression_error:
		return "", compression_error
	if not raw:
		return "", None

	if not raw.lower().startswith("data:image/"):
		return "", "Некорректный формат изображения"

	parts = raw.split(",", 1)
	if len(parts) != 2:
		return "", "Некорректный формат изображения"

	header = parts[0].strip().lower()
	if ";base64" not in header:
		return "", "Некорректный формат изображения"

	subtype_raw = header[len("data:image/") :].split(";", 1)[0].strip()
	if not subtype_raw:
		return "", "Некорректный формат изображения"

	ext = "webp"

	payload = re.sub(r"\s+", "", parts[1])
	if not payload:
		return "", "Некорректные base64-данные изображения"

	padding = (-len(payload)) % 4
	if padding:
		payload += "=" * padding

	try:
		binary = base64.b64decode(payload, validate=False)
	except (binascii.Error, ValueError):
		return "", "Некорректные base64-данные изображения"

	if len(binary) > 5 * 1024 * 1024:
		return "", "Изображение слишком большое (максимум 5MB)"

	service_images_dir = Path(settings.MEDIA_ROOT) / "service_images"
	service_images_dir.mkdir(parents=True, exist_ok=True)
	file_name = f"tenant-{tenant}-partner-{partner_profile_id}-{uuid.uuid4().hex}.{ext}"
	file_path = service_images_dir / file_name
	file_path.write_bytes(binary)
	return f"/api/v1/partner/service-images/{file_name}", None


def delete_managed_image(image_url: str):
	url = str(image_url or "").strip().rstrip("/")
	prefixes = {
		"/api/v1/partner/service-images/": "service_images",
		"/api/v1/partner/profile-images/": "profile_images",
	}
	for prefix, directory in prefixes.items():
		if not url.startswith(prefix):
			continue
		file_name = url[len(prefix) :]
		if not re.match(r"^[a-zA-Z0-9._-]+$", file_name):
			return
		file_path = Path(settings.MEDIA_ROOT) / directory / file_name
		try:
			file_path.unlink(missing_ok=True)
		except OSError:
			pass
		return


def resolve_service_image_payload(raw_image_url, raw_image_base64, tenant: str, partner_profile_id: int):
	image_url = normalize_service_image_url(str(raw_image_url or "").strip())
	image_base64 = str(raw_image_base64 or "").strip()

	if image_base64.startswith("data:image/"):
		uploaded_url, upload_error = save_service_image_from_base64(image_base64, tenant, partner_profile_id)
		if upload_error:
			return None, None, upload_error
		return uploaded_url, "", None

	if image_url:
		return image_url, "", None

	legacy_url = normalize_service_image_url(image_base64)
	if legacy_url.startswith("/api/v1/partner/service-images/"):
		return legacy_url, "", None

	return "", image_base64, None


def normalize_service_details(category_name: str, raw_details):
	if raw_details is None:
		return {}, None
	if not isinstance(raw_details, dict):
		return {}, "details должен быть объектом"

	cleaned = {}

	if category_name == "Спорт":
		max_people, max_error = parse_positive_int(raw_details.get("max_people"), "max_people")
		if max_error:
			return {}, max_error
		min_people, min_error = parse_positive_int(raw_details.get("min_people"), "min_people")
		if min_error:
			return {}, min_error
		if min_people is not None and max_people is not None and min_people > max_people:
			return {}, "min_people не может быть больше max_people"
		if max_people is not None:
			cleaned["max_people"] = max_people
		if min_people is not None:
			cleaned["min_people"] = min_people

	if category_name == "Кафе и рестораны":
		table_capacity, table_error = parse_positive_int(raw_details.get("table_capacity"), "table_capacity")
		if table_error:
			return {}, table_error
		hold_minutes, hold_error = parse_positive_int(raw_details.get("hold_minutes"), "hold_minutes")
		if hold_error:
			return {}, hold_error
		if table_capacity is not None:
			cleaned["table_capacity"] = table_capacity
		if hold_minutes is not None:
			cleaned["hold_minutes"] = hold_minutes

	return cleaned, None


WEEKDAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
VALID_WEEKDAY_SET = set(WEEKDAY_ORDER)
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def default_working_schedule():
	schedule = []
	for day in WEEKDAY_ORDER:
		is_weekend = day in {"sat", "sun"}
		schedule.append(
			{
				"day": day,
				"is_day_off": is_weekend,
				"start_time": "09:00",
				"end_time": "18:00",
				"break_start": "13:00",
				"break_end": "14:00",
			}
		)
	return schedule


def normalize_working_schedule(raw_schedule):
	if raw_schedule is None:
		return default_working_schedule(), None
	if not isinstance(raw_schedule, list):
		return None, "working_schedule должен быть массивом"

	by_day = {}
	for raw_item in raw_schedule:
		if not isinstance(raw_item, dict):
			return None, "working_schedule содержит некорректный элемент"

		day = str(raw_item.get("day") or "").strip().lower()
		if day not in VALID_WEEKDAY_SET:
			return None, "working_schedule.day должен быть одним из mon..sun"
		if day in by_day:
			return None, f"working_schedule содержит дубли для дня {day}"

		is_day_off = parse_bool(raw_item.get("is_day_off"), False)
		start_time = str(raw_item.get("start_time") or "").strip()
		end_time = str(raw_item.get("end_time") or "").strip()
		break_start = str(raw_item.get("break_start") or "").strip()
		break_end = str(raw_item.get("break_end") or "").strip()

		if not is_day_off:
			if not TIME_RE.match(start_time):
				return None, f"start_time для {day} должен быть в формате HH:MM"
			if not TIME_RE.match(end_time):
				return None, f"end_time для {day} должен быть в формате HH:MM"
			if start_time >= end_time:
				return None, f"Для дня {day} start_time должен быть раньше end_time"

			if bool(break_start) != bool(break_end):
				return None, f"Для дня {day} укажите оба поля break_start и break_end"
			if break_start and break_end:
				if not TIME_RE.match(break_start) or not TIME_RE.match(break_end):
					return None, f"Перерыв для дня {day} должен быть в формате HH:MM"
				if not (start_time < break_start < break_end < end_time):
					return None, f"Перерыв для дня {day} должен быть внутри рабочего времени"
		else:
			start_time = ""
			end_time = ""
			break_start = ""
			break_end = ""

		by_day[day] = {
			"day": day,
			"is_day_off": is_day_off,
			"start_time": start_time,
			"end_time": end_time,
			"break_start": break_start,
			"break_end": break_end,
		}

	normalized = []
	for day in WEEKDAY_ORDER:
		if day in by_day:
			normalized.append(by_day[day])
		else:
			is_weekend = day in {"sat", "sun"}
			normalized.append(
				{
					"day": day,
					"is_day_off": is_weekend,
					"start_time": "09:00",
					"end_time": "18:00",
					"break_start": "13:00",
					"break_end": "14:00",
				}
			)

	return normalized, None


def parse_service_names(raw: str):
	return [item.strip() for item in str(raw or "").splitlines() if item.strip()]


def to_aware_datetime(value):
	if value is None:
		return None
	if timezone.is_naive(value):
		return timezone.make_aware(value, timezone.get_current_timezone())
	return value


def build_service_duration_map(tenant: str, partner_profile=None):
	duration_map = {}
	items = Service.objects.filter(tenant_slug=tenant)
	if partner_profile is not None:
		items = items.filter(partner_profile=partner_profile)
	for service in items:
		duration = service.duration_minutes if service.duration_minutes and service.duration_minutes > 0 else 60
		service_name = (service.name or "").strip().lower()
		if service_name:
			if service_name in duration_map:
				duration_map[service_name] = min(duration_map[service_name], duration)
			else:
				duration_map[service_name] = duration
		kind_name = (service.kind.name if service.kind else "").strip().lower()
		if kind_name:
			if kind_name in duration_map:
				duration_map[kind_name] = min(duration_map[kind_name], duration)
			else:
				duration_map[kind_name] = duration
	return duration_map


def resolve_booking_duration_minutes(service_name: str, duration_map) -> int:
	names = parse_service_names(service_name)
	if not names:
		names = [str(service_name or "").strip()]
	minutes = 0
	for name in names:
		minutes += duration_map.get(name.lower(), 60)
	return minutes if minutes > 0 else 60


def has_booking_overlap(
	tenant: str,
	manager_name: str,
	starts_at,
	duration_minutes: int,
	partner_profile=None,
	exclude_booking_id: int = None,
):
	manager = str(manager_name or "").strip()
	if not manager:
		return False

	start_dt = to_aware_datetime(starts_at)
	if start_dt is None:
		return False
	end_dt = start_dt + timedelta(minutes=max(1, int(duration_minutes or 60)))

	duration_map = build_service_duration_map(tenant, partner_profile=partner_profile)
	items = Booking.objects.filter(tenant_slug=tenant, manager_name__iexact=manager)
	if partner_profile is not None:
		items = items.filter(partner_profile=partner_profile)
	if exclude_booking_id is not None:
		items = items.exclude(id=exclude_booking_id)

	for existing in items:
		existing_start = to_aware_datetime(existing.starts_at)
		if existing_start is None:
			continue
		existing_duration = resolve_booking_duration_minutes(existing.service_name, duration_map)
		existing_end = existing_start + timedelta(minutes=max(1, existing_duration))
		if start_dt < existing_end and existing_start < end_dt:
			return True

	return False


def serialize_partner_profile(profile: PartnerProfile):
	return {
		"full_name": profile.user.first_name,
		"email": profile.user.email,
		"phone": profile.phone,
		"company_name": profile.company_name,
		"business_category": profile.business_category,
		"address": profile.address,
	}


class PartnerProfileView(APIView):
	def get(self, request):
		if request_actor_role(request) == "manager":
			return Response({"message": "Доступ запрещен для роли manager"}, status=403)

		profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		return Response(serialize_partner_profile(profile))

	def patch(self, request):
		if request_actor_role(request) == "manager":
			return Response({"message": "Доступ запрещен для роли manager"}, status=403)

		profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		full_name = request.data.get("full_name")
		if full_name is not None:
			value = str(full_name).strip()
			if not value:
				return Response({"message": "full_name не может быть пустым"}, status=400)
			profile.user.first_name = value

		email = request.data.get("email")
		if email is not None:
			value = str(email).strip().lower()
			if not value:
				return Response({"message": "email не может быть пустым"}, status=400)
			existing = (
				PartnerProfile.objects.select_related("user")
				.filter(Q(user__username__iexact=value) | Q(user__email__iexact=value))
				.exclude(id=profile.id)
				.first()
			)
			if existing is not None:
				return Response({"message": "Пользователь с таким email уже существует"}, status=409)
			profile.user.username = value
			profile.user.email = value

		phone = request.data.get("phone")
		if phone is not None:
			value = str(phone).strip()
			if not value:
				return Response({"message": "phone не может быть пустым"}, status=400)
			profile.phone = value

		company_name = request.data.get("company_name")
		if company_name is not None:
			profile.company_name = str(company_name).strip()

		business_category = request.data.get("business_category")
		if business_category is not None:
			profile.business_category = str(business_category).strip()

		address = request.data.get("address")
		if address is not None:
			profile.address = str(address).strip()

		profile.user.save()
		profile.save()
		profile.refresh_from_db()

		return Response(serialize_partner_profile(profile))


class CategoryListCreateView(APIView):
	def get(self, request):
		tenant = tenant_from_request(request)
		partner_category = partner_category_from_request(request)
		items = Category.objects.filter(tenant_slug=tenant)
		if partner_category:
			items = items.filter(name=partner_category)
		items = items.order_by("-id")
		return Response([
			{
				"id": item.id,
				"name": item.name,
				"is_active": item.is_active,
			}
			for item in items
		])

	def post(self, request):
		return Response({"message": "Справочник категорий редактируется только администратором"}, status=403)


class ServiceKindListCreateView(APIView):
	def get(self, request):
		tenant = tenant_from_request(request)
		partner_category = partner_category_from_request(request)
		category_id = request.query_params.get("category")
		items = ServiceKind.objects.filter(tenant_slug=tenant).select_related("category")
		if partner_category:
			items = items.filter(category__name=partner_category)
		if category_id:
			items = items.filter(category_id=category_id)
		items = items.order_by("category__name", "name")
		return Response([
			{
				"id": item.id,
				"name": item.name,
				"category": item.category_id,
				"category_name": item.category.name,
				"is_active": item.is_active,
			}
			for item in items
		])

	def post(self, request):
		return Response({"message": "Справочник видов услуг редактируется только администратором"}, status=403)


class ServiceListCreateView(APIView):
	def get(self, request):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		include_image = parse_bool(request.query_params.get("include_image"), True)
		partner_category = partner_category_from_request(request)
		items = Service.objects.filter(tenant_slug=tenant, partner_profile=partner_profile).select_related("category", "kind")
		if partner_category:
			items = items.filter(category__name=partner_category)
		items = items.order_by("-id")
		return Response([
			{
				"id": item.id,
				"name": item.name,
				"partner_profile": item.partner_profile_id,
				"category": item.category_id,
				"category_name": item.category.name,
				"kind": item.kind_id,
				"kind_name": item.kind.name if item.kind else None,
				"details": item.details or {},
				"description": item.description,
				"duration_minutes": item.duration_minutes,
				"price": str(item.price) if item.price is not None else None,
				"discount_percent": item.discount_percent,
				"is_subscription": item.is_subscription,
				"image_url": normalize_service_image_url(item.image_url),
				"image_base64": item.image_base64 if include_image else "",
				"is_promo": item.is_promo,
				"is_active": item.is_active,
			}
			for item in items
		])

	def post(self, request):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		partner_category = partner_category_from_request(request)
		name = (request.data.get("name") or "").strip()
		category_id = request.data.get("category")
		if not name or not category_id:
			return Response({"message": "name и category обязательны"}, status=400)

		category = Category.objects.filter(id=category_id, tenant_slug=tenant).first()
		if not category:
			return Response({"message": "Категория не найдена"}, status=400)
		if partner_category and category.name != partner_category:
			return Response({"message": "Можно создавать услуги только в выбранной категории бизнеса"}, status=400)

		kind_id = request.data.get("kind")
		if not kind_id:
			return Response({"message": "kind обязателен"}, status=400)
		kind = ServiceKind.objects.filter(id=kind_id, tenant_slug=tenant, category=category).first()
		if not kind:
			return Response({"message": "Направление услуги не найдено для выбранной категории"}, status=400)

		discount_percent = int(request.data.get("discount_percent") or 0)
		discount_percent = max(0, min(100, discount_percent))
		is_subscription = parse_bool(request.data.get("is_subscription"), True)
		is_promo = parse_bool(request.data.get("is_promo"), discount_percent > 0)
		normalized_details, details_error = normalize_service_details(category.name, request.data.get("details"))
		if details_error:
			return Response({"message": details_error}, status=400)

		image_url, image_base64, image_error = resolve_service_image_payload(
			request.data.get("image_url"),
			request.data.get("image_base64"),
			tenant,
			partner_profile.id,
		)
		if image_error:
			return Response({"message": image_error}, status=400)

		item = Service.objects.create(
			tenant_slug=tenant,
			partner_profile=partner_profile,
			name=name,
			category=category,
			kind=kind,
			details=normalized_details,
			description=(request.data.get("description") or "").strip(),
			duration_minutes=int(request.data.get("duration_minutes") or 60),
			price=request.data.get("price") or 0,
			discount_percent=discount_percent,
			is_subscription=is_subscription,
			image_url=image_url,
			image_base64=image_base64,
			is_promo=is_promo,
			is_active=parse_bool(request.data.get("is_active"), True),
		)

		return Response(
			{
				"id": item.id,
				"name": item.name,
				"partner_profile": item.partner_profile_id,
				"category": item.category_id,
				"category_name": category.name,
				"kind": item.kind_id,
				"kind_name": item.kind.name if item.kind else None,
				"details": item.details or {},
				"description": item.description,
				"duration_minutes": item.duration_minutes,
				"price": str(item.price) if item.price is not None else None,
				"discount_percent": item.discount_percent,
				"is_subscription": item.is_subscription,
				"image_url": normalize_service_image_url(item.image_url),
				"image_base64": item.image_base64,
				"is_promo": item.is_promo,
				"is_active": item.is_active,
			},
			status=201,
		)


class ServiceDetailView(APIView):
	def patch(self, request, service_id: int):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		partner_category = partner_category_from_request(request)
		item = Service.objects.filter(
			id=service_id,
			tenant_slug=tenant,
			partner_profile=partner_profile,
		).select_related("category", "kind").first()
		if not item:
			return Response({"message": "Услуга не найдена"}, status=404)
		if partner_category and item.category.name != partner_category:
			return Response({"message": "Услуга недоступна для текущей категории бизнеса"}, status=403)

		name = request.data.get("name")
		if name is not None:
			name = str(name).strip()
			if not name:
				return Response({"message": "name не может быть пустым"}, status=400)
			item.name = name

		category_id = request.data.get("category")
		if category_id is not None:
			category = Category.objects.filter(id=category_id, tenant_slug=tenant).first()
			if not category:
				return Response({"message": "Категория не найдена"}, status=400)
			if partner_category and category.name != partner_category:
				return Response({"message": "Нельзя сменить категорию услуги"}, status=400)
			item.category = category
		else:
			category = item.category

		kind_id = request.data.get("kind")
		if kind_id is not None:
			kind = ServiceKind.objects.filter(id=kind_id, tenant_slug=tenant, category=item.category).first()
			if not kind:
				return Response({"message": "Направление услуги не найдено для выбранной категории"}, status=400)
			item.kind = kind
		elif category_id is not None and item.kind.category_id != item.category_id:
			return Response({"message": "При смене категории выберите направление услуги"}, status=400)

		details = request.data.get("details")
		if details is not None:
			normalized_details, details_error = normalize_service_details(item.category.name, details)
			if details_error:
				return Response({"message": details_error}, status=400)
			item.details = normalized_details

		description = request.data.get("description")
		if description is not None:
			item.description = str(description).strip()

		duration_minutes = request.data.get("duration_minutes")
		if duration_minutes is not None:
			item.duration_minutes = int(duration_minutes)

		price = request.data.get("price")
		if price is not None:
			item.price = price

		discount_percent = request.data.get("discount_percent")
		if discount_percent is not None:
			parsed_discount = int(discount_percent)
			item.discount_percent = max(0, min(100, parsed_discount))

		is_subscription = request.data.get("is_subscription")
		if is_subscription is not None:
			item.is_subscription = parse_bool(is_subscription, item.is_subscription)

		image_url = request.data.get("image_url")
		image_base64 = request.data.get("image_base64")
		previous_image_url = item.image_url
		if image_url is not None or image_base64 is not None:
			resolved_image_url, resolved_image_base64, image_error = resolve_service_image_payload(
				image_url if image_url is not None else item.image_url,
				image_base64 if image_base64 is not None else item.image_base64,
				tenant,
				partner_profile.id,
			)
			if image_error:
				return Response({"message": image_error}, status=400)
			item.image_url = resolved_image_url
			item.image_base64 = resolved_image_base64

		is_promo = request.data.get("is_promo")
		if is_promo is not None:
			item.is_promo = parse_bool(is_promo, item.is_promo)
		elif discount_percent is not None:
			item.is_promo = item.discount_percent > 0

		is_active = request.data.get("is_active")
		if is_active is not None:
			item.is_active = parse_bool(is_active, item.is_active)

		item.save()
		if item.image_url != previous_image_url:
			delete_managed_image(previous_image_url)
		item.refresh_from_db()

		return Response(
			{
				"id": item.id,
				"name": item.name,
				"partner_profile": item.partner_profile_id,
				"category": item.category_id,
				"category_name": item.category.name,
				"kind": item.kind_id,
				"kind_name": item.kind.name if item.kind else None,
				"details": item.details or {},
				"description": item.description,
				"duration_minutes": item.duration_minutes,
				"price": str(item.price) if item.price is not None else None,
				"discount_percent": item.discount_percent,
				"is_subscription": item.is_subscription,
				"image_url": normalize_service_image_url(item.image_url),
				"image_base64": item.image_base64,
				"is_promo": item.is_promo,
				"is_active": item.is_active,
			}
		)


class ManagerListCreateView(APIView):
	def get(self, request):
		if request_actor_role(request) == "manager":
			return Response({"message": "Доступ запрещен для роли manager"}, status=403)

		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		items = (
			Manager.objects.filter(tenant_slug=tenant, partner_profile=partner_profile)
			.order_by("-id")
		)
		return Response([
			{
				"id": item.id,
				"full_name": item.full_name,
				"phone": item.phone,
				"email": item.email,
				"photo_url": normalize_profile_image_url(item.photo_url),
				"is_active": item.is_active,
			}
			for item in items
		])

	def post(self, request):
		if request_actor_role(request) == "manager":
			return Response({"message": "Доступ запрещен для роли manager"}, status=403)

		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		full_name = (request.data.get("full_name") or "").strip()
		phone = normalize_ru_phone((request.data.get("phone") or "").strip())
		email = (request.data.get("email") or "").strip().lower()
		password = (request.data.get("password") or "").strip()
		photo_base64 = (request.data.get("photo_base64") or "").strip()
		if not full_name or not phone or not email or not password:
			return Response({"message": "full_name, phone, email и password обязательны"}, status=400)
		if not PHONE_RU_RE.match(phone):
			return Response({"message": "Телефон должен быть в формате +7XXXXXXXXXX"}, status=400)
		if len(password) < 8:
			return Response({"message": "Пароль менеджера должен быть не короче 8 символов"}, status=400)
		photo_url, photo_error = save_profile_image_from_base64(photo_base64, tenant, partner_profile.id, "manager")
		if photo_error:
			return Response({"message": photo_error}, status=400)

		existing_user = (
			User.objects.select_related("partner_profile")
			.filter(Q(username__iexact=email) | Q(email__iexact=email))
			.first()
		)
		if existing_user:
			existing_profile = getattr(existing_user, "partner_profile", None)
			existing_role = (existing_profile.user_type if existing_profile else "").strip().lower()
			if existing_role == "partner":
				return Response({"message": "Этот логин уже зарегистрирован как партнер"}, status=409)
			if existing_role == "manager":
				return Response({"message": "Этот логин уже зарегистрирован как менеджер"}, status=409)
			return Response({"message": "Пользователь с таким логином уже существует"}, status=409)

		manager_user = User.objects.create_user(
			username=email,
			email=email,
			password=password,
			first_name=full_name,
		)
		PartnerProfile.objects.create(
			user=manager_user,
			phone=phone,
			user_type="manager",
			company_name=partner_profile.company_name,
			address=partner_profile.address,
			business_category=partner_profile.business_category,
		)

		item = Manager.objects.create(
			tenant_slug=tenant,
			partner_profile=partner_profile,
			full_name=full_name,
			phone=phone,
			email=email,
			photo_url=photo_url,
			is_active=parse_bool(request.data.get("is_active"), True),
		)

		return Response(
			{
				"id": item.id,
				"full_name": item.full_name,
				"phone": item.phone,
				"email": item.email,
				"photo_url": normalize_profile_image_url(item.photo_url),
				"is_active": item.is_active,
			},
			status=201,
		)


class ManagerDetailView(APIView):
	def patch(self, request, manager_id: int):
		if request_actor_role(request) == "manager":
			return Response({"message": "Доступ запрещен для роли manager"}, status=403)

		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		item = Manager.objects.filter(
			id=manager_id,
			tenant_slug=tenant,
			partner_profile=partner_profile,
		).first()
		if not item:
			return Response({"message": "Специалист не найден"}, status=404)

		full_name = request.data.get("full_name")
		if full_name is not None:
			value = str(full_name).strip()
			if not value:
				return Response({"message": "full_name не может быть пустым"}, status=400)
			item.full_name = value
			manager_user = User.objects.filter(Q(username__iexact=item.email) | Q(email__iexact=item.email)).first()
			if manager_user:
				manager_user.first_name = value
				manager_user.save(update_fields=["first_name"])

		phone = request.data.get("phone")
		if phone is not None:
			value = normalize_ru_phone(str(phone).strip())
			if not value:
				return Response({"message": "phone не может быть пустым"}, status=400)
			if not PHONE_RU_RE.match(value):
				return Response({"message": "Телефон должен быть в формате +7XXXXXXXXXX"}, status=400)
			item.phone = value
			manager_user = User.objects.filter(Q(username__iexact=item.email) | Q(email__iexact=item.email)).first()
			if manager_user and hasattr(manager_user, "partner_profile"):
				manager_user.partner_profile.phone = value
				manager_user.partner_profile.save(update_fields=["phone"])

		email = request.data.get("email")
		if email is not None:
			value = str(email).strip().lower()
			if not value:
				return Response({"message": "email не может быть пустым"}, status=400)
			existing_user = (
				User.objects.select_related("partner_profile")
				.filter(Q(username__iexact=value) | Q(email__iexact=value))
				.exclude(Q(username__iexact=item.email) | Q(email__iexact=item.email))
				.first()
			)
			if existing_user:
				existing_profile = getattr(existing_user, "partner_profile", None)
				existing_role = (existing_profile.user_type if existing_profile else "").strip().lower()
				if existing_role == "partner":
					return Response({"message": "Этот логин уже зарегистрирован как партнер"}, status=409)
				if existing_role == "manager":
					return Response({"message": "Этот логин уже зарегистрирован как менеджер"}, status=409)
				return Response({"message": "Пользователь с таким логином уже существует"}, status=409)

			manager_user = User.objects.filter(Q(username__iexact=item.email) | Q(email__iexact=item.email)).first()
			if manager_user:
				manager_user.username = value
				manager_user.email = value
				manager_user.save(update_fields=["username", "email"])
			item.email = value

		photo_base64 = request.data.get("photo_base64")
		previous_photo_url = item.photo_url
		if photo_base64 is not None:
			photo_url, photo_error = save_profile_image_from_base64(
				str(photo_base64).strip(), tenant, partner_profile.id, "manager"
			)
			if photo_error:
				return Response({"message": photo_error}, status=400)
			item.photo_url = photo_url
			item.photo_base64 = ""

		is_active = request.data.get("is_active")
		if is_active is not None:
			item.is_active = parse_bool(is_active, item.is_active)

		item.save()
		if item.photo_url != previous_photo_url:
			delete_managed_image(previous_photo_url)

		return Response(
			{
				"id": item.id,
				"full_name": item.full_name,
				"phone": item.phone,
				"email": item.email,
				"photo_url": normalize_profile_image_url(item.photo_url),
				"is_active": item.is_active,
			}
		)


class SpecialistListCreateView(APIView):
	def get(self, request):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		include_photo = parse_bool(request.query_params.get("include_photo"), True)
		include_schedule = parse_bool(request.query_params.get("include_schedule"), True)
		items = (
			Specialist.objects.filter(tenant_slug=tenant, partner_profile=partner_profile)
			.prefetch_related("capabilities__service")
			.order_by("-id")
		)
		return Response([
			{
				"id": item.id,
				"full_name": item.full_name,
				"description": item.description,
				"phone": item.phone,
				"email": item.email,
				"photo_url": normalize_profile_image_url(item.photo_url) if include_photo else "",
				"working_schedule": (item.working_schedule or default_working_schedule()) if include_schedule else [],
				"service_ids": [cap.service_id for cap in item.capabilities.all()],
				"service_names": [cap.service.name for cap in item.capabilities.all()],
				"is_active": item.is_active,
			}
			for item in items
		])

	def post(self, request):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		full_name = (request.data.get("full_name") or "").strip()
		phone = (request.data.get("phone") or "").strip()
		email = (request.data.get("email") or "").strip().lower()
		description = (request.data.get("description") or "").strip()
		photo_base64 = (request.data.get("photo_base64") or "").strip()
		service_ids = request.data.get("service_ids") or []
		working_schedule_raw = request.data.get("working_schedule")
		if not full_name:
			return Response({"message": "full_name обязателен"}, status=400)
		if not isinstance(service_ids, list):
			return Response({"message": "service_ids должен быть массивом"}, status=400)
		photo_url, photo_error = save_profile_image_from_base64(
			photo_base64, tenant, partner_profile.id, "specialist"
		)
		if photo_error:
			return Response({"message": photo_error}, status=400)

		normalized_schedule, schedule_error = normalize_working_schedule(working_schedule_raw)
		if schedule_error:
			return Response({"message": schedule_error}, status=400)

		parsed_service_ids = []
		for raw_id in service_ids:
			try:
				parsed_service_ids.append(int(raw_id))
			except (TypeError, ValueError):
				return Response({"message": "service_ids содержит некорректный id"}, status=400)

		available_services = {
			service.id: service
			for service in Service.objects.filter(
				tenant_slug=tenant,
				partner_profile=partner_profile,
				id__in=parsed_service_ids,
			)
		}
		for service_id in parsed_service_ids:
			if service_id not in available_services:
				return Response({"message": f"Услуга {service_id} не найдена"}, status=400)

		item = Specialist.objects.create(
			tenant_slug=tenant,
			partner_profile=partner_profile,
			full_name=full_name,
			description=description,
			phone=phone,
			email=email,
			photo_url=photo_url,
			working_schedule=normalized_schedule,
			is_active=parse_bool(request.data.get("is_active"), True),
		)

		capabilities = []
		for service_id in parsed_service_ids:
			capabilities.append(SpecialistService(specialist=item, service=available_services[service_id]))
		if capabilities:
			SpecialistService.objects.bulk_create(capabilities)

		item.refresh_from_db()
		assigned_capabilities = list(item.capabilities.select_related("service"))
		return Response(
			{
				"id": item.id,
				"full_name": item.full_name,
				"description": item.description,
				"phone": item.phone,
				"email": item.email,
				"photo_url": normalize_profile_image_url(item.photo_url),
				"working_schedule": item.working_schedule or default_working_schedule(),
				"service_ids": [cap.service_id for cap in assigned_capabilities],
				"service_names": [cap.service.name for cap in assigned_capabilities],
				"is_active": item.is_active,
			},
			status=201,
		)


class SpecialistDetailView(APIView):
	def get(self, request, specialist_id: int):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		item = (
			Specialist.objects.filter(
				id=specialist_id,
				tenant_slug=tenant,
				partner_profile=partner_profile,
			)
			.prefetch_related("capabilities__service")
			.first()
		)
		if not item:
			return Response({"message": "Специалист не найден"}, status=404)

		capabilities = list(item.capabilities.all())
		return Response(
			{
				"id": item.id,
				"full_name": item.full_name,
				"description": item.description,
				"phone": item.phone,
				"email": item.email,
				"photo_url": normalize_profile_image_url(item.photo_url),
				"working_schedule": item.working_schedule or default_working_schedule(),
				"service_ids": [cap.service_id for cap in capabilities],
				"service_names": [cap.service.name for cap in capabilities],
				"is_active": item.is_active,
			}
		)

	def patch(self, request, specialist_id: int):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		item = Specialist.objects.filter(
			id=specialist_id,
			tenant_slug=tenant,
			partner_profile=partner_profile,
		).first()
		if not item:
			return Response({"message": "Специалист не найден"}, status=404)

		full_name = request.data.get("full_name")
		if full_name is not None:
			value = str(full_name).strip()
			if not value:
				return Response({"message": "full_name не может быть пустым"}, status=400)
			item.full_name = value

		description = request.data.get("description")
		if description is not None:
			item.description = str(description).strip()

		phone = request.data.get("phone")
		if phone is not None:
			item.phone = str(phone).strip()

		email = request.data.get("email")
		if email is not None:
			item.email = str(email).strip().lower()

		photo_base64 = request.data.get("photo_base64")
		previous_photo_url = item.photo_url
		if photo_base64 is not None:
			photo_url, photo_error = save_profile_image_from_base64(
				str(photo_base64).strip(), tenant, partner_profile.id, "specialist"
			)
			if photo_error:
				return Response({"message": photo_error}, status=400)
			item.photo_url = photo_url
			item.photo_base64 = ""

		working_schedule_raw = request.data.get("working_schedule")
		if working_schedule_raw is not None:
			normalized_schedule, schedule_error = normalize_working_schedule(working_schedule_raw)
			if schedule_error:
				return Response({"message": schedule_error}, status=400)
			item.working_schedule = normalized_schedule

		is_active = request.data.get("is_active")
		if is_active is not None:
			item.is_active = parse_bool(is_active, item.is_active)

		item.save()
		if item.photo_url != previous_photo_url:
			delete_managed_image(previous_photo_url)

		service_ids = request.data.get("service_ids")
		if service_ids is not None:
			if not isinstance(service_ids, list):
				return Response({"message": "service_ids должен быть массивом"}, status=400)

			parsed_service_ids = []
			for raw_id in service_ids:
				try:
					parsed_service_ids.append(int(raw_id))
				except (TypeError, ValueError):
					return Response({"message": "service_ids содержит некорректный id"}, status=400)

			available_services = {
				service.id: service
				for service in Service.objects.filter(
					tenant_slug=tenant,
					partner_profile=partner_profile,
					id__in=parsed_service_ids,
				)
			}
			for service_id in parsed_service_ids:
				if service_id not in available_services:
					return Response({"message": f"Услуга {service_id} не найдена"}, status=400)

			SpecialistService.objects.filter(specialist=item).exclude(service_id__in=parsed_service_ids).delete()
			existing_service_ids = set(
				SpecialistService.objects.filter(specialist=item, service_id__in=parsed_service_ids)
				.values_list("service_id", flat=True)
			)
			to_create = [
				SpecialistService(specialist=item, service=available_services[service_id])
				for service_id in parsed_service_ids
				if service_id not in existing_service_ids
			]
			if to_create:
				SpecialistService.objects.bulk_create(to_create)

		assigned_capabilities = list(item.capabilities.select_related("service"))
		return Response(
			{
				"id": item.id,
				"full_name": item.full_name,
				"description": item.description,
				"phone": item.phone,
				"email": item.email,
				"photo_url": normalize_profile_image_url(item.photo_url),
				"working_schedule": item.working_schedule or default_working_schedule(),
				"service_ids": [cap.service_id for cap in assigned_capabilities],
				"service_names": [cap.service.name for cap in assigned_capabilities],
				"is_active": item.is_active,
			}
		)


class BookingListCreateView(APIView):
	def get(self, request):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		items = Booking.objects.filter(tenant_slug=tenant, partner_profile=partner_profile).order_by("-id")
		return Response([
			{
				"id": item.id,
				"service_name": item.service_name,
				"manager_name": item.manager_name,
				"starts_at": item.starts_at.isoformat(),
				"client_name": item.client_name,
				"client_phone": item.client_phone,
				"status": item.status,
			}
			for item in items
		])

	def post(self, request):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		starts_at_raw = request.data.get("starts_at")
		starts_at = parse_datetime(str(starts_at_raw)) if starts_at_raw else None
		if starts_at is None:
			return Response({"message": "starts_at должен быть в ISO формате"}, status=400)

		required = ["service_name", "client_name", "client_phone"]
		for field in required:
			if not str(request.data.get(field) or "").strip():
				return Response({"message": f"{field} обязателен"}, status=400)

		service_name = str(request.data.get("service_name")).strip()
		manager_name = str(request.data.get("manager_name") or "").strip() or None
		duration_minutes = resolve_booking_duration_minutes(
			service_name,
			build_service_duration_map(tenant, partner_profile=partner_profile),
		)
		if manager_name and has_booking_overlap(
			tenant,
			manager_name,
			starts_at,
			duration_minutes,
			partner_profile=partner_profile,
		):
			return Response({"message": "У специалиста уже есть запись на это время"}, status=409)

		item = Booking.objects.create(
			tenant_slug=tenant,
			partner_profile=partner_profile,
			service_name=service_name,
			manager_name=manager_name,
			starts_at=starts_at,
			client_name=str(request.data.get("client_name")).strip(),
			client_phone=str(request.data.get("client_phone")).strip(),
			status=str(request.data.get("status") or "booked").strip(),
		)
		return Response({"id": item.id, "ok": True}, status=201)


class BookingDetailView(APIView):
	def patch(self, request, booking_id: int):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		item = Booking.objects.filter(id=booking_id, tenant_slug=tenant, partner_profile=partner_profile).first()
		if not item:
			return Response({"message": "Запись не найдена"}, status=404)

		if "service_name" in request.data:
			value = str(request.data.get("service_name") or "").strip()
			if not value:
				return Response({"message": "service_name обязателен"}, status=400)
			item.service_name = value

		if "manager_name" in request.data:
			item.manager_name = str(request.data.get("manager_name") or "").strip() or None

		if "starts_at" in request.data:
			starts_at_raw = request.data.get("starts_at")
			starts_at = parse_datetime(str(starts_at_raw)) if starts_at_raw else None
			if starts_at is None:
				return Response({"message": "starts_at должен быть в ISO формате"}, status=400)
			item.starts_at = starts_at

		if "client_name" in request.data:
			value = str(request.data.get("client_name") or "").strip()
			if not value:
				return Response({"message": "client_name обязателен"}, status=400)
			item.client_name = value

		if "client_phone" in request.data:
			value = str(request.data.get("client_phone") or "").strip()
			if not value:
				return Response({"message": "client_phone обязателен"}, status=400)
			item.client_phone = value

		if "status" in request.data:
			item.status = str(request.data.get("status") or "booked").strip() or "booked"

		duration_minutes = resolve_booking_duration_minutes(
			item.service_name,
			build_service_duration_map(tenant, partner_profile=partner_profile),
		)
		if item.manager_name and has_booking_overlap(
			tenant,
			item.manager_name,
			item.starts_at,
			duration_minutes,
			partner_profile=partner_profile,
			exclude_booking_id=item.id,
		):
			return Response({"message": "У специалиста уже есть запись на это время"}, status=409)

		item.save()
		return Response(
			{
				"id": item.id,
				"service_name": item.service_name,
				"manager_name": item.manager_name,
				"starts_at": item.starts_at.isoformat(),
				"client_name": item.client_name,
				"client_phone": item.client_phone,
				"status": item.status,
			}
		)


class ServiceImageUploadView(APIView):
	def post(self, request):
		partner_profile, error_response = get_partner_profile(request)
		if error_response is not None:
			return error_response

		tenant = tenant_from_request(request)
		image_base64 = request.data.get("image_base64")
		image_url, image_error = save_service_image_from_base64(image_base64, tenant, partner_profile.id)
		if image_error:
			return Response({"message": image_error}, status=400)

		return Response({"image_url": image_url}, status=201)


class ServiceImageView(APIView):
	def get(self, request, file_name: str):
		if not re.match(r"^[a-zA-Z0-9._-]+$", file_name or ""):
			return Response({"message": "Некорректное имя файла"}, status=400)

		file_path = Path(settings.MEDIA_ROOT) / "service_images" / file_name
		if not file_path.exists() or not file_path.is_file():
			return Response({"message": "Изображение не найдено"}, status=404)

		ext = file_path.suffix.lower()
		content_type = "application/octet-stream"
		if ext == ".png":
			content_type = "image/png"
		elif ext in {".jpg", ".jpeg"}:
			content_type = "image/jpeg"
		elif ext == ".webp":
			content_type = "image/webp"
		elif ext == ".gif":
			content_type = "image/gif"

		response = FileResponse(open(file_path, "rb"), content_type=content_type)
		response["Cache-Control"] = "public, max-age=31536000, immutable"
		return response


class ProfileImageView(APIView):
	def get(self, request, file_name: str):
		if not re.match(r"^[a-zA-Z0-9._-]+$", file_name or ""):
			return Response({"message": "Некорректное имя файла"}, status=400)

		file_path = Path(settings.MEDIA_ROOT) / "profile_images" / file_name
		if not file_path.exists() or not file_path.is_file():
			return Response({"message": "Изображение не найдено"}, status=404)

		response = FileResponse(open(file_path, "rb"), content_type="image/webp")
		response["Cache-Control"] = "public, max-age=31536000, immutable"
		return response

# Create your views here.
