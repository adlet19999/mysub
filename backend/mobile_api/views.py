import re
import uuid
import json
import hashlib
from urllib.parse import urlsplit
from io import BytesIO
from pathlib import Path
from datetime import date, datetime, time, timedelta

import jwt
from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction, OperationalError, IntegrityError, DatabaseError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import FileResponse, Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.exceptions import APIException

from common_api.models import PartnerProfile
from common_api.views import normalize_ru_phone
from partner_api.models import Booking, BookingPass, Service, Specialist
from partner_api.views import (
    CLOSED_BOOKING_STATUSES,
    booking_schedule_error,
    calculate_booking_pricing,
    group_booking_error,
    has_booking_overlap,
    has_client_booking_overlap,
    pass_visits_error,
    save_booking_pass,
    pass_booking_pricing,
    serialize_booking_pass,
    to_aware_datetime,
)
from partner_api.grouping import attach_group_session
from partner_api.intervals import slot_error, slot_interval
from partner_api.restaurant import create_restaurant_booking, is_restaurant, restaurant_booking_data, party_size_error, choose_table, HOLD

from .models import CustomerChild, CustomerProfile, MobileRefreshSession, MobileBookingRecord, MobileBookingRequest
from .booking_contract import booking_end, booking_identity, booking_revision, owned_bookings, status_group
from .catalog_contract import category_code, booking_category, partner_rating, resource_data, resource_error
from .models import BookingResource
from common_api.models import BusinessCategory
from types import SimpleNamespace
from copy import copy
from .otp import send_challenge, verify_challenge
from .serializers import (
    LogoutRequestSerializer,
    AuthenticationResponseSerializer,
    AvatarUploadRequestSerializer,
    AvatarUploadResponseSerializer,
    AvailabilityResponseSerializer,
    CatalogPartnerListResponseSerializer,
    CatalogServiceListResponseSerializer,
    CatalogSpecialistListResponseSerializer,
    CityListResponseSerializer,
    CustomerResponseSerializer,
    CustomerUpdateRequestSerializer,
    MobileBookingCreateRequestSerializer,
    MobileBookingListResponseSerializer,
    MobileBookingSerializer,
    BookingQuoteSerializer,
    RefreshTokenResponseSerializer,
    RefreshTokenRequestSerializer,
    SendCodeResponseSerializer,
    SendCodeRequestSerializer,
    VerifyCodeRequestSerializer,
)
from .models import City


PHONE_RE = re.compile(r"^\+7[0-9]{10}$")
CHILD_NAME_RE = re.compile(r"^[^\d_]{1,50}$")
MAX_CHILDREN = 2
MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 25_000_000
AVATAR_URL_PREFIX = "/api/v1/mobile/avatar-images/"


def error_response(status_code, code, message, field=None, retry_after=None):
    details = []
    if field:
        details.append({"field": field, "message": message})
    error = {"code": code, "message": message, "details": details}
    if retry_after is not None:
        error["retry_after"] = retry_after
    response = Response({"error": error}, status=status_code)
    if retry_after is not None:
        response["Retry-After"] = str(retry_after)
    if status_code == 401:
        response["WWW-Authenticate"] = "Bearer"
    return response


def challenge_error(error):
    return error_response(*error[:3], retry_after=error[3] if len(error) > 3 else None)


def validation_response(errors, path=""):
    if isinstance(errors, dict):
        field = next(iter(errors))
        return validation_response(errors[field], f"{path}.{field}" if path else field)
    if isinstance(errors, list) and isinstance(errors[0], (dict, list)):
        return validation_response(errors[0], f"{path}.0")
    return error_response(400, "VALIDATION_ERROR", str(errors[0]), path)


def serialize_quote(partner, service, specialist, starts, pricings, table=None, resource=None):
    from decimal import Decimal
    visits = [{"starts_at": start.isoformat(), "ends_at": (start + timedelta(minutes=120 if table else service.duration_minutes)).isoformat(),
               "base_price": str(pricing["base_price"]), "discount_amount": str(pricing["discount_amount"]),
               "final_price": str(pricing["final_price"])} for start, pricing in zip(starts, pricings)]
    return {"partner_id": partner.id, "service_id": service.id, "specialist_id": specialist.id if specialist else None,
            "currency": "KZT", "is_reserved": False, "visits": visits,
            "base_price": str(sum((pricing["base_price"] for pricing in pricings), Decimal("0.00"))),
            "discount_amount": str(sum((pricing["discount_amount"] for pricing in pricings), Decimal("0.00"))),
            "final_price": str(sum((pricing["final_price"] for pricing in pricings), Decimal("0.00"))),
            "resource_id": resource.id if resource else None, "table_id": table.id if table else None}


def table_booking_snapshot(booking):
    return {"kind": "table", "id": booking.table_id, "name": booking.manager_name,
            "capacity": booking.table.capacity, "party_size": booking.party_size} if booking.table_id else {}


def create_mobile_customer(phone, language):
    with transaction.atomic():
        user = User.objects.create_user(username=f"mobile:{uuid.uuid4().hex}", password=None)
        return CustomerProfile.objects.create(user=user, phone=phone, language=language)


def get_request_language(request):
    language = (request.data.get("language") or request.headers.get("Accept-Language") or "ru").lower()
    return language[:2] if language[:2] in {"ru", "kk", "en"} else "ru"


def age_on(date_of_birth, on_date):
    return on_date.year - date_of_birth.year - ((on_date.month, on_date.day) < (date_of_birth.month, date_of_birth.day))


def attendee_eligibility_error(service, attendee, starts_at):
    rules = service.details or {}
    audience, minimum, maximum = (rules.get(key) for key in ("audience", "min_age", "max_age"))
    if (audience not in {None, "any", "adult", "child"}
            or any(value is not None and (type(value) is not int or not 0 <= value <= 120) for value in (minimum, maximum))
            or (minimum is not None and maximum is not None and minimum > maximum)):
        return error_response(409, "AUDIENCE_NOT_CONFIGURED", "Правила возраста услуги заполнены некорректно")
    kind = attendee.get("type")
    if (audience == "child" and kind != "child") or (audience == "adult" and kind == "child"):
        return error_response(400, "ATTENDEE_NOT_ELIGIBLE", "Участник не подходит для услуги", "attendee")
    if kind == "child":
        try:
            birthday = date.fromisoformat(attendee.get("date_of_birth", ""))
        except (TypeError, ValueError):
            return error_response(409, "ATTENDEE_DETAILS_REQUIRED", "Для участника нет достоверной даты рождения", "attendee")
        age = age_on(birthday, timezone.localdate(starts_at))
        if age < 0 or age >= 18 or (minimum is not None and age < minimum) or (maximum is not None and age > maximum):
            return error_response(400, "ATTENDEE_NOT_ELIGIBLE", "Возраст не подходит для услуги на выбранную дату", "attendee")
    return None


def serialize_child(child):
    age = age_on(child.date_of_birth, timezone.localdate())
    return {
        "id": child.id,
        "name": child.name,
        "date_of_birth": child.date_of_birth.isoformat(),
        "age": age,
    }


def serialize_customer(customer, request=None):
    children = list(customer.children.order_by("id"))
    avatar_url = customer.avatar_url or None
    if avatar_url and avatar_url.startswith("/") and request:
        avatar_url = request.build_absolute_uri(avatar_url)
    result = {
        "id": str(customer.id),
        "phone": customer.phone,
        "name": customer.user.first_name or None,
        "email": customer.user.email or None,
        "avatar_url": avatar_url,
        "city_id": customer.city_id,
        "city_name": customer.city.name if customer.city_id else None,
        "language": customer.language,
        "is_profile_complete": bool(customer.user.first_name and customer.city_id),
        "agreement_accepted": customer.agreement_accepted,
        "agreement_version": customer.agreement_version or None,
        "children": [serialize_child(child) for child in children],
        "max_children": MAX_CHILDREN,
        "created_at": customer.created_at.isoformat(),
        "updated_at": customer.updated_at.isoformat(),
    }
    result["revision"] = hashlib.sha256(json.dumps({**result, "avatar_url": customer.avatar_url}, sort_keys=True).encode()).hexdigest()
    return result


def catalog_public_url(request, value):
    if value and value.startswith("/"):
        return request.build_absolute_uri(value)
    return value or ""


def catalog_partner_name(partner):
    return partner.company_name or partner.user.get_full_name() or partner.user.username


def serialize_catalog_partner(partner, request):
    photo_urls = [
        catalog_public_url(request, item)
        for item in (partner.business_photo_urls or [])
        if isinstance(item, str) and item
    ]
    primary_photo = catalog_public_url(request, partner.business_photo_url)
    if primary_photo and primary_photo not in photo_urls:
        photo_urls.insert(0, primary_photo)
    return {
        "id": partner.id,
        "name": catalog_partner_name(partner),
        "category": partner.business_category or "",
        "city": partner.city or "",
        "address": partner.address or "",
        "description": partner.description or "",
        "photo_urls": photo_urls,
        "phone": normalize_ru_phone(partner.phone) if PHONE_RE.fullmatch(normalize_ru_phone(partner.phone)) else None,
        "website": partner.website or None,
        "instagram": partner.instagram or None,
        "working_hours": partner.working_hours or None,
        "time_zone": timezone.get_current_timezone_name(),
        "category_id": BusinessCategory.objects.filter(name=partner.business_category, is_archived=False).values_list("id", flat=True).first(),
        "category_code": category_code(partner.business_category),
        "verification_status": "unavailable",
        **partner_rating(partner),
    }


def serialize_catalog_service(service, request):
    partner = service.partner_profile
    return {
        "id": service.id,
        "partner_id": partner.id,
        "partner_name": catalog_partner_name(partner),
        "name": service.name,
        "category": service.category.name,
        "category_id": BusinessCategory.objects.filter(name=service.category.name, is_archived=False).values_list("id", flat=True).first(),
        "service_category_id": service.category_id,
        "category_code": category_code(service.category.name),
        "booking_category_code": booking_category(service),
        "kind": service.kind.name if service.kind_id else None,
        "description": service.description or "",
        "duration_minutes": 120 if is_restaurant(partner) else service.duration_minutes or 60,
        "slot_interval_minutes": service.slot_interval_minutes or 30,
        "booking_mode": "table" if is_restaurant(partner) else ("resource" if booking_category(service) in {"photo_studio", "recreation"} else "specialist"),
        "price": str(service.price) if service.price is not None else None,
        "service_type": service.service_type,
        "is_pass": service.is_pass,
        "visit_count": service.visit_count,
        "pass_price_mode": service.pass_price_mode,
        "image_url": catalog_public_url(request, service.image_url),
        "resource_ids": list(service.mobile_resources.filter(partner=partner, is_active=True).values_list("id", flat=True)),
        "audience": (service.details or {}).get("audience"),
        "min_age": (service.details or {}).get("min_age"),
        "max_age": (service.details or {}).get("max_age"),
        "requires_occurrence": bool((service.details or {}).get("require_occurrence", False)),
        "discount_percent": service.discount_percent,
        "is_promo": service.is_promo,
        "currency": "KZT",
    }


def serialize_catalog_specialist(specialist, request):
    capabilities = [capability for capability in specialist.capabilities.all() if capability.service.is_active]
    return {
        "id": specialist.id,
        "full_name": specialist.full_name,
        "description": specialist.description or "",
        "photo_url": catalog_public_url(request, specialist.photo_url),
        "service_ids": [capability.service_id for capability in capabilities],
        "service_names": [capability.service.name for capability in capabilities],
    }


def active_catalog_partners():
    return PartnerProfile.objects.select_related("user").filter(user_type="partner", user__is_active=True)

def catalog_service_visible(service):
    if is_restaurant(service.partner_profile) and service.is_pass:
        return False
    return not group_booking_error([service])


def is_mobile_booking_cancellable(booking):
    starts_at = to_aware_datetime(booking.starts_at)
    return bool(
        starts_at
        and starts_at > timezone.now()
        and status_group(booking) == "upcoming"
    )


def serialize_mobile_booking(booking, include_group=True):
    partner = booking.partner_profile
    service_ids, specialist_id, duration = booking_identity(booking)
    record = getattr(booking, "mobile_record", None)
    review = getattr(booking, "mobile_review", None)
    own_review = review if review and record and review.customer_id == record.customer_id else None
    end = booking_end(booking)
    cancellable = is_mobile_booking_cancellable(booking)
    restaurant = restaurant_booking_data(booking)
    if restaurant is not None:
        restaurant["table_snapshot"] = record.resource_snapshot if record and record.resource_snapshot.get("kind") == "table" else None
    pass_data = serialize_booking_pass(booking)
    if pass_data is not None:
        own_visits = list(booking.booking_pass.bookings.filter(
            tenant_slug=booking.tenant_slug, mobile_record__customer_id=record.customer_id,
        ).only("id", "status")) if record and record.customer_id else []
        own_ids = {visit.id for visit in own_visits}
        pass_data["visits"] = [visit for visit in pass_data["visits"] if visit["id"] in own_ids]
        pass_data["completed_visits"] = sum(status_group(visit) == "completed" for visit in own_visits)
        pass_data["owned_visit_count"] = len(own_ids)
        pass_data["is_complete"] = len(own_ids) == pass_data["visit_count"]
    booking_group = None
    if include_group and record and record.batch_id:
        siblings = Booking.objects.filter(tenant_slug=booking.tenant_slug, mobile_record__batch_id=record.batch_id, mobile_record__customer_id=record.customer_id).select_related("partner_profile__user", "mobile_record").order_by("starts_at", "id")
        group_entries = []
        for item in siblings:
            entry = serialize_mobile_booking(item, include_group=False)
            entry.pop("booking_group")
            group_entries.append(entry)
        booking_group = {"id": str(record.batch_id), "entries": group_entries, "is_complete": True}
    return {
        "id": booking.id,
        "partner_id": partner.id,
        "partner_name": catalog_partner_name(partner),
        "service_name": booking.service_name,
        "specialist_name": booking.manager_name or "",
        "service_id": service_ids[0] if len(service_ids) == 1 else None,
        "service_ids": service_ids,
        "specialist_id": specialist_id,
        "starts_at": timezone.localtime(booking.starts_at).isoformat(),
        "ends_at": timezone.localtime(end).isoformat() if end else None,
        "duration_minutes": duration,
        "currency": "KZT",
        "status": booking.status,
        "status_group": status_group(booking),
        "revision": booking_revision(booking),
        "comment": record.comment if record else "",
        "attendee": record.attendee if record else {},
        "vehicle": record.vehicle if record else {},
        "resource": record.resource_snapshot if record and record.resource_id else None,
        "booking_group": booking_group,
        "base_price": str(booking.base_price),
        "discount_amount": str(booking.discount_amount),
        "final_price": str(booking.final_price),
        "is_cancellable": cancellable,
        "cancellation_reason": None if cancellable else ("CANCELLATION_DEADLINE" if status_group(booking) == "upcoming" else "BOOKING_STATE"),
        "is_reschedulable": cancellable and len(service_ids) == 1 and bool(duration),
        "is_reviewable": status_group(booking) == "completed" and not review,
        "review": {"id": own_review.id, "booking_id": own_review.booking_id, "rating": own_review.rating,
                   "comment": own_review.comment, "language": own_review.language, "state": own_review.state,
                   "created_at": own_review.created_at.isoformat()} if own_review else None,
        "created_at": booking.created_at.isoformat(),
        "booking_pass": pass_data,
        "restaurant": restaurant,
    }


def delete_stored_avatar(avatar_url):
    path = urlsplit(avatar_url or "").path
    if not path.startswith(AVATAR_URL_PREFIX):
        return
    file_name = path.removeprefix(AVATAR_URL_PREFIX)
    if not re.fullmatch(r"customer-[0-9]+-[a-f0-9]{32}\.webp", file_name):
        return
    file_path = Path(settings.MEDIA_ROOT) / "customer_avatars" / file_name
    if file_path.exists():
        file_path.unlink()


def save_customer_avatar(uploaded_file, customer_id):
    if uploaded_file.size > MAX_AVATAR_SIZE_BYTES:
        return None, "Изображение слишком большое (максимум 5 MB)"
    try:
        with Image.open(uploaded_file) as probe:
            probe.verify()
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as source:
            if source.width * source.height > MAX_AVATAR_PIXELS:
                return None, "Разрешение изображения слишком большое"
            image = ImageOps.exif_transpose(source)
            image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            if image.mode == "RGBA":
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format="WEBP", quality=82, method=6)
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError, ValueError):
        return None, "Не удалось обработать изображение"

    avatar_dir = Path(settings.MEDIA_ROOT) / "customer_avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"customer-{customer_id}-{uuid.uuid4().hex}.webp"
    (avatar_dir / file_name).write_bytes(output.getvalue())
    return f"{AVATAR_URL_PREFIX}{file_name}", None


def token_payload(customer, token_type, expires_at, token_id=None):
    now = timezone.now()
    payload = {
        "sub": str(customer.id),
        "type": token_type,
        "iss": "mysub-mobile-api",
        "aud": "mysub-mobile-app",
        "iat": now,
        "exp": expires_at,
    }
    if token_id:
        payload["jti"] = token_id
    return payload


def issue_tokens(customer):
    now = timezone.now()
    access_expires_at = now + timedelta(seconds=settings.MOBILE_JWT_ACCESS_TTL_SECONDS)
    refresh_expires_at = now + timedelta(seconds=settings.MOBILE_JWT_REFRESH_TTL_SECONDS)
    refresh_id = uuid.uuid4().hex
    MobileRefreshSession.objects.create(
        customer=customer,
        token_id=refresh_id,
        expires_at=refresh_expires_at,
    )
    access_token = jwt.encode(
        token_payload(customer, "access", access_expires_at, refresh_id),
        settings.MOBILE_JWT_SECRET,
        algorithm="HS256",
    )
    refresh_token = jwt.encode(
        token_payload(customer, "refresh", refresh_expires_at, refresh_id),
        settings.MOBILE_JWT_SECRET,
        algorithm="HS256",
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.MOBILE_JWT_ACCESS_TTL_SECONDS,
    }


def decode_token(raw_token, expected_type):
    try:
        payload = jwt.decode(
            raw_token,
            settings.MOBILE_JWT_SECRET,
            algorithms=["HS256"],
            issuer="mysub-mobile-api",
            audience="mysub-mobile-app",
        )
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    if not isinstance(subject, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", subject) or int(subject) > 9223372036854775807:
        return None
    return payload if payload.get("type") == expected_type else None


class MobileAPIView(APIView):
    throttle_classes = [ScopedRateThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if not response.has_header("Cache-Control"):
            response["Cache-Control"] = "no-store"
        return response

    def handle_exception(self, exc):
        if isinstance(exc, Http404):
            return error_response(404, "NOT_FOUND", "Ресурс не найден")
        if isinstance(exc, APIException):
            status_code = exc.status_code
            codes = {400: "VALIDATION_ERROR", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
                     404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 415: "UNSUPPORTED_MEDIA_TYPE",
                     429: "RATE_LIMIT"}
            return error_response(status_code, codes.get(status_code, "API_ERROR"), str(exc.detail),
                                  retry_after=getattr(exc, "wait", None))
        return super().handle_exception(exc)


class MobileAuthenticatedView(MobileAPIView):
    customer = None

    def dispatch(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                return super().dispatch(request, *args, **kwargs)
        except OperationalError as exc:
            code = getattr(exc.__cause__, "sqlstate", None) or getattr(exc.__cause__, "pgcode", None)
            if code not in {"40P01", "40001", "55P03"}:
                raise
            return self.finalize_response(self.request, error_response(
                409, "CONCURRENT_UPDATE", "Данные изменяются другим запросом; перечитайте состояние", retry_after=1,
            ), *args, **kwargs)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        auth_header = request.headers.get("Authorization", "")
        scheme, _, raw_token = auth_header.partition(" ")
        payload = decode_token(raw_token, "access") if scheme.lower() == "bearer" else None
        if not payload:
            self.permission_denied(request, message="UNAUTHORIZED")
        customers = CustomerProfile.objects.select_related("user", "city")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            customers = customers.select_for_update(of=("self",), no_key=True)
        self.customer = customers.filter(id=payload.get("sub"), user__is_active=True).first()
        if not self.customer:
            self.permission_denied(request, message="UNAUTHORIZED")
        self.mobile_session = MobileRefreshSession.objects.filter(
            customer=self.customer, token_id=payload.get("jti"),
            revoked_at__isnull=True, expires_at__gt=timezone.now(),
        ).first()
        if not self.mobile_session:
            self.permission_denied(request, message="UNAUTHORIZED")

    def handle_exception(self, exc):
        if getattr(exc, "detail", None) == "UNAUTHORIZED":
            return error_response(401, "UNAUTHORIZED", "Недействительный access token")
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class MobileCitiesView(MobileAPIView):
    @extend_schema(
        tags=['0. Справочники'],
        summary='Получить список городов',
        description='Используйте `id` выбранного города в поле `city_id` при заполнении профиля. Название города вручную передавать не нужно.',
        responses={200: CityListResponseSerializer},
    )
    def get(self, request):
        cities = City.objects.filter(is_active=True)
        return Response({"data": [{"id": city.id, "name": city.name} for city in cities]})


class MobileCatalogPartnersView(MobileAPIView):
    @extend_schema(
        tags=["4. Каталог и запись"],
        summary="Получить партнёров",
        description="Публичный каталог активных партнёров. Можно отфильтровать по городу, категории бизнеса или части названия.",
        parameters=[
            OpenApiParameter(name="city", type=str, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="category", type=str, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="search", type=str, location=OpenApiParameter.QUERY, required=False),
        ],
        responses={200: CatalogPartnerListResponseSerializer},
    )
    def get(self, request):
        items = active_catalog_partners()
        city = (request.query_params.get("city") or "").strip()
        category = (request.query_params.get("category") or "").strip()
        search = (request.query_params.get("search") or "").strip()
        if city:
            items = items.filter(city__iexact=city)
        if category:
            items = items.filter(business_category__iexact=category)
        if search:
            items = items.filter(company_name__icontains=search)
        return Response({"data": [serialize_catalog_partner(item, request) for item in items.order_by("company_name", "id")]})


class MobileCatalogServicesView(MobileAPIView):
    @extend_schema(
        tags=["4. Каталог и запись"],
        summary="Получить услуги всех партнёров",
        description="Возвращает активные услуги активных партнёров. Фильтры можно комбинировать.",
        parameters=[
            OpenApiParameter(name="partner_id", type=int, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="category", type=str, location=OpenApiParameter.QUERY, required=False),
            OpenApiParameter(name="city", type=str, location=OpenApiParameter.QUERY, required=False),
        ],
        responses={200: CatalogServiceListResponseSerializer},
    )
    def get(self, request):
        items = Service.objects.filter(
            tenant_slug="public",
            is_active=True,
            partner_profile__user_type="partner",
            partner_profile__user__is_active=True,
        ).select_related("partner_profile__user", "category", "kind")
        partner_id = request.query_params.get("partner_id")
        category = (request.query_params.get("category") or "").strip()
        city = (request.query_params.get("city") or "").strip()
        if partner_id:
            try:
                items = items.filter(partner_profile_id=int(partner_id))
            except ValueError:
                return error_response(400, "VALIDATION_ERROR", "partner_id должен быть числом", "partner_id")
        if category:
            items = items.filter(category__name__iexact=category)
        if city:
            items = items.filter(partner_profile__city__iexact=city)
        return Response({"data": [serialize_catalog_service(item, request) for item in items.order_by("partner_profile__company_name", "name", "id") if catalog_service_visible(item)]})


class MobileCatalogPartnerServicesView(MobileAPIView):
    @extend_schema(
        tags=["4. Каталог и запись"],
        summary="Получить услуги партнёра",
        responses={200: CatalogServiceListResponseSerializer, 404: None},
    )
    def get(self, request, partner_id: int):
        partner = active_catalog_partners().filter(id=partner_id).first()
        if partner is None:
            return error_response(404, "PARTNER_NOT_FOUND", "Партнёр не найден")
        items = Service.objects.filter(
            tenant_slug="public", partner_profile=partner, is_active=True
        ).select_related("partner_profile__user", "category", "kind")
        return Response({"data": [serialize_catalog_service(item, request) for item in items.order_by("name", "id") if catalog_service_visible(item)]})


class MobileCatalogPartnerSpecialistsView(MobileAPIView):
    @extend_schema(
        tags=["4. Каталог и запись"],
        summary="Получить специалистов партнёра",
        parameters=[OpenApiParameter(name="service_id", type=int, location=OpenApiParameter.QUERY, required=False)],
        responses={200: CatalogSpecialistListResponseSerializer, 400: None, 404: None},
    )
    def get(self, request, partner_id: int):
        partner = active_catalog_partners().filter(id=partner_id).first()
        if partner is None:
            return error_response(404, "PARTNER_NOT_FOUND", "Партнёр не найден")
        if is_restaurant(partner):
            return Response({"data": []})
        items = Specialist.objects.filter(
            tenant_slug="public",
            partner_profile=partner,
            is_active=True,
            capabilities__service__is_active=True,
        ).prefetch_related("capabilities__service")
        service_id = request.query_params.get("service_id")
        if service_id:
            try:
                items = items.filter(capabilities__service_id=int(service_id))
            except ValueError:
                return error_response(400, "VALIDATION_ERROR", "service_id должен быть числом", "service_id")
        return Response({"data": [serialize_catalog_specialist(item, request) for item in items.distinct().order_by("full_name", "id")]})


class MobileCatalogSpecialistAvailabilityView(MobileAPIView):
    @extend_schema(
        tags=["4. Каталог и запись"],
        summary="Получить свободное время специалиста",
        description="Слоты возвращаются в часовом поясе Asia/Almaty с учётом графика, длительности услуги и занятости. Шаг задаётся в предложении; для старых предложений — 30 минут.",
        parameters=[
            OpenApiParameter(
                name="date",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Дата в формате YYYY-MM-DD",
            ),
            OpenApiParameter(name="service_id", type=int, location=OpenApiParameter.QUERY, required=True),
        ],
        responses={200: AvailabilityResponseSerializer, 400: None, 404: None},
    )
    def get(self, request, partner_id: int, specialist_id: int):
        partner = active_catalog_partners().filter(id=partner_id).first()
        if partner is None:
            return error_response(404, "PARTNER_NOT_FOUND", "Партнёр не найден")
        specialist = Specialist.objects.filter(
            id=specialist_id,
            tenant_slug="public",
            partner_profile=partner,
            is_active=True,
        ).first()
        if specialist is None:
            return error_response(404, "SPECIALIST_NOT_FOUND", "Специалист не найден")
        try:
            service_id = int(request.query_params.get("service_id") or "")
        except ValueError:
            return error_response(400, "VALIDATION_ERROR", "service_id обязателен и должен быть числом", "service_id")
        service = Service.objects.filter(
            id=service_id,
            tenant_slug="public",
            partner_profile=partner,
            is_active=True,
        ).first()
        if service is None or not specialist.capabilities.filter(service_id=service.id).exists():
            return error_response(404, "SERVICE_UNAVAILABLE", "Услуга недоступна у выбранного специалиста", "service_id")
        if not catalog_service_visible(service):
            return error_response(404, "SERVICE_UNAVAILABLE", "Формат услуги недоступен", "service_id")
        if service.service_type == "group" and (service.details or {}).get("require_occurrence"):
            return error_response(400, "CLASS_REQUIRED", "Используйте group-sessions для выбора существующего занятия", "service_id")
        try:
            requested_date = date.fromisoformat(request.query_params.get("date") or "")
        except ValueError:
            return error_response(400, "VALIDATION_ERROR", "date обязателен и должен быть в формате YYYY-MM-DD", "date")
        if not timezone.localdate() <= requested_date <= timezone.localdate() + timedelta(days=365):
            return error_response(400, "BOOKING_HORIZON", "Дата должна быть в ближайшие 365 дней", "date")

        duration_minutes = service.duration_minutes or 60
        day_start = timezone.make_aware(
            datetime.combine(requested_date, time.min), timezone.get_current_timezone()
        )
        slots = []
        interval = slot_interval([service], default=30)
        for minute_offset in range(0, 24 * 60 - duration_minutes + 1, interval):
            starts_at = day_start + timedelta(minutes=minute_offset)
            if starts_at <= timezone.now():
                continue
            if booking_schedule_error(specialist, starts_at, duration_minutes) is not None:
                continue
            if has_booking_overlap(
                specialist.tenant_slug,
                specialist.full_name,
                starts_at,
                duration_minutes,
                partner_profile=partner,
                service=service,
                specialist_id=specialist.id,
            ):
                continue
            slots.append(timezone.localtime(starts_at).strftime("%H:%M"))

        return Response({
            "date": requested_date.isoformat(),
            "time_zone": timezone.get_current_timezone_name(),
            "duration_minutes": duration_minutes,
            "slot_interval_minutes": interval,
            "slots": slots,
        })


class MobileCatalogRestaurantAvailabilityView(MobileAPIView):
    @extend_schema(
        tags=["4. Каталог и запись"],
        summary="Свободное время столиков без выбора столика",
        parameters=[
            OpenApiParameter(name="date", type=str, required=True, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="service_id", type=int, required=True, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="party_size", type=int, required=True, location=OpenApiParameter.QUERY),
        ],
        responses={200: AvailabilityResponseSerializer, 400: None, 404: None},
    )
    def get(self, request, partner_id):
        from partner_api.restaurant import party_size_error
        from partner_api.restaurant_views import restaurant_slots
        partner = active_catalog_partners().filter(id=partner_id).first()
        if partner is None:
            return error_response(404, "PARTNER_NOT_FOUND", "Партнёр не найден")
        if not is_restaurant(partner):
            from .catalog_views import service_availability
            return service_availability(request, partner)
        try:
            requested_date = date.fromisoformat(request.query_params.get("date", ""))
            service_id = int(request.query_params.get("service_id", ""))
            party_size = int(request.query_params.get("party_size", ""))
        except (TypeError, ValueError):
            return error_response(400, "VALIDATION_ERROR", "Укажите дату, предложение и количество гостей")
        if not timezone.localdate() <= requested_date <= timezone.localdate() + timedelta(days=365):
            return error_response(400, "BOOKING_HORIZON", "Дата должна быть в ближайшие 365 дней", "date")
        service = Service.objects.filter(id=service_id, partner_profile=partner, tenant_slug="public", is_active=True, service_type="individual", is_pass=False).first()
        if not service or party_size_error(party_size) or requested_date < timezone.localdate():
            return error_response(400, "VALIDATION_ERROR", "Проверьте предложение, количество гостей и дату")
        return Response(restaurant_slots(partner, "public", requested_date, service, party_size))


class MobileBookingsView(MobileAuthenticatedView):
    @extend_schema(
        tags=["4. Каталог и запись"],
        auth=[{"MobileBearer": []}],
        summary="Получить мои записи",
        description="Возвращает записи только авторизованного клиента, включая отменённые для истории.",
        responses={200: MobileBookingListResponseSerializer, 401: None},
    )
    def get(self, request):
        items = (
            owned_bookings(self.customer)
            .select_related("partner_profile__user", "table", "mobile_record", "mobile_review", "group_session__group")
            .prefetch_related("extensions")
            .order_by("-starts_at", "-id")
        )
        data = [serialize_mobile_booking(item) for item in items]
        return Response({"data": data, "total": len(data), "is_complete": True})

    @extend_schema(
        tags=["4. Каталог и запись"],
        auth=[{"MobileBearer": []}],
        summary="Записаться к специалисту",
        description=(
            "Создаёт запись для авторизованного клиента. Сервер повторно проверяет активность партнёра, "
            "услугу специалиста, график, перерывы и пересечения записей. Время должно быть будущим "
            "и соответствовать интервалу предложения. Для ресторанов specialist_id не нужен: "
            "передайте party_size, столик назначается автоматически на два часа."
        ),
        request=MobileBookingCreateRequestSerializer,
        responses={201: MobileBookingSerializer, 200: MobileBookingSerializer, 400: None, 401: None, 404: None, 409: None},
    )
    @transaction.atomic
    def post(self, request):
        serializer = MobileBookingCreateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_response(serializer.errors)
        unknown = set(request.data) - set(serializer.fields)
        if unknown:
            return error_response(400, "UNSUPPORTED_FIELD", "Поле не поддерживается", sorted(unknown)[0])
        data = serializer.validated_data
        if "vehicle" in data:
            data["vehicle"]["registration_plate"] = " ".join(data["vehicle"]["registration_plate"].split()).upper()
        entries = data.get("entries")
        if entries and any(field in data for field in ("service_id", "specialist_id", "starts_at", "visits", "group_session_id", "resource_id")):
            return error_response(400, "CONFLICTING_BOOKING_FIELDS", "Передайте entries или поля одной записи")
        if not entries and ("service_id" not in data or "starts_at" not in data):
            return error_response(400, "VALIDATION_ERROR", "Укажите service_id и starts_at")
        if entries and not data.get("request_id"):
            return error_response(400, "REQUEST_ID_REQUIRED", "Для нескольких услуг нужен request_id", "request_id")
        if entries and len({timezone.localdate(entry["starts_at"]) for entry in entries}) != 1:
            return error_response(400, "ENTRY_DATE", "Услуги одного визита должны начинаться в одну местную дату", "entries")
        customer = CustomerProfile.objects.select_for_update(of=("self",), no_key=True).select_related("user").get(id=self.customer.id)
        request_id = data.get("request_id")
        payload = json.loads(json.dumps(data, default=str, sort_keys=True))
        if request_id:
            previous = MobileBookingRequest.objects.filter(customer=customer, operation="create", request_id=request_id).first()
            if previous:
                if previous.payload != payload:
                    return error_response(409, "REQUEST_CONFLICT", "request_id уже использован для другого запроса")
                booking = owned_bookings(customer).filter(id=previous.booking_ids[0]).first()
                if not booking:
                    return error_response(409, "BOOKING_UNAVAILABLE", "Ранее созданная запись больше недоступна")
                return Response(serialize_mobile_booking(booking))
        attendee = data.get("attendee", {"type": "self"})
        if attendee["type"] == "child":
            child = customer.children.filter(id=attendee.get("child_id")).first()
            if not child or serialize_child(child)["age"] >= 18:
                return error_response(400, "ATTENDEE_UNAVAILABLE", "Ребёнок недоступен", "attendee")
            attendee = {"type": "child", "child_id": child.id, "name": child.name, "date_of_birth": child.date_of_birth.isoformat()}
        else:
            if attendee.get("child_id"):
                return error_response(400, "VALIDATION_ERROR", "child_id допустим только для ребёнка", "attendee")
            attendee = {"type": "self", "name": customer.user.get_full_name()}
        bookings = []
        batch_id = uuid.uuid4() if entries else None
        if entries:
            partner = active_catalog_partners().filter(id=data["partner_id"]).first()
            if not partner or category_code(partner.business_category) not in {"medical", "beauty"}:
                return error_response(400, "MULTI_SERVICE_UNSUPPORTED", "Несколько отдельных услуг доступны для медицины и салонов")
        previous_end = None
        comments = {}
        for entry in payload.get("entries") or [payload]:
            single = {key: value for key, value in payload.items() if key not in {"entries", "expected_final_price"}}
            single.update(entry)
            result = self._create(SimpleNamespace(data=single))
            if result.status_code >= 400:
                transaction.set_rollback(True)
                return result
            booking = Booking.objects.get(id=result.data["id"])
            if entries and (booking.booking_pass_id or booking.group_session_id or booking.table_id):
                transaction.set_rollback(True)
                return error_response(400, "MULTI_SERVICE_UNSUPPORTED", "Каждая строка должна быть отдельной индивидуальной услугой")
            if previous_end and booking.starts_at < previous_end:
                transaction.set_rollback(True)
                return error_response(400, "ENTRY_ORDER", "Услуги должны идти по порядку без пересечений", "entries")
            previous_end = booking_end(booking)
            created = list(booking.booking_pass.bookings.all()) if booking.booking_pass_id else [booking]
            bookings.extend(created)
            for item in created:
                comments[item.id] = single.get("comment", "")
        if "expected_final_price" in data and sum(item.final_price for item in bookings) != data["expected_final_price"]:
            transaction.set_rollback(True)
            return error_response(409, "PRICE_CHANGED", "Цена изменилась; запросите актуальный расчёт", "expected_final_price")
        for item in bookings:
            resource = BookingResource.objects.filter(id=data.get("resource_id"), partner=item.partner_profile, is_active=True).first()
            MobileBookingRecord.objects.update_or_create(
                booking=item, defaults={"customer": customer, "owner_claimed": True,
                                        "comment": comments[item.id], "attendee": attendee, "batch_id": batch_id,
                                        "vehicle": data.get("vehicle", {}), "resource": resource,
                                        "resource_snapshot": {**resource_data(resource), "party_size": item.party_size} if resource else table_booking_snapshot(item)},
            )
        if request_id:
            MobileBookingRequest.objects.create(customer=customer, operation="create", request_id=request_id,
                                                payload=payload, booking_ids=[item.id for item in bookings])
        return Response(serialize_mobile_booking(Booking.objects.get(id=bookings[0].id)), status=201)

    def _create(self, request, quote=False):
        try:
            partner_id = int(request.data.get("partner_id") or "")
            service_id = int(request.data.get("service_id") or "")
        except (TypeError, ValueError):
            return error_response(400, "VALIDATION_ERROR", "partner_id и service_id должны быть числами")

        starts_at_raw = request.data.get("starts_at")
        try:
            starts_at = parse_datetime(str(starts_at_raw)) if starts_at_raw else None
        except ValueError:
            starts_at = None
        if starts_at is None:
            return error_response(400, "VALIDATION_ERROR", "starts_at должен быть в ISO 8601 формате", "starts_at")
        starts_at = to_aware_datetime(starts_at)
        if starts_at <= timezone.now():
            return error_response(400, "VALIDATION_ERROR", "Нельзя записаться на прошедшее время", "starts_at")
        if timezone.localdate(starts_at) > timezone.localdate() + timedelta(days=365):
            return error_response(400, "BOOKING_HORIZON", "Запись доступна на 365 дней вперёд", "starts_at")

        with transaction.atomic():
            customer = (
                CustomerProfile.objects.select_for_update(of=("self",), no_key=True)
                .select_related("user")
                .filter(id=self.customer.id)
                .first()
            )
            client_name = customer.user.get_full_name().strip() if customer else ""
            if not client_name:
                return error_response(409, "PROFILE_INCOMPLETE", "Заполните имя в профиле перед записью", "name")
            attendee_context = request.data.get("attendee", {"type": "self"})

            partner = active_catalog_partners().select_for_update().filter(id=partner_id).first()
            if partner is None:
                return error_response(404, "PARTNER_NOT_FOUND", "Партнёр не найден")
            if is_restaurant(partner):
                if attendee_context.get("type", "self") != "self":
                    return error_response(400, "ATTENDEE_NOT_SUPPORTED", "Бронь столика оформляется на владельца аккаунта; гостей укажите в party_size", "attendee")
                service = Service.objects.filter(id=service_id, tenant_slug="public", partner_profile=partner, is_active=True).first()
                if service is None:
                    return error_response(404, "SERVICE_NOT_FOUND", "Предложение не найдено")
                if service.price is None or service.price < 0:
                    return error_response(409, "PRICE_NOT_CONFIGURED", "У предложения нет корректной цены")
                if any(request.data.get(field) for field in ("resource_id", "vehicle", "group_session_id", "specialist_id")):
                    return error_response(400, "RESTAURANT_FIELDS", "Для ресторана передайте количество гостей, без специалиста или ресурса")
                if "visits" in request.data:
                    return error_response(400, "VALIDATION_ERROR", "Для брони столика выберите одну дату")
                message = party_size_error(request.data.get("party_size")) or slot_error([service], starts_at, default=30)
                if message:
                    return error_response(400, "VALIDATION_ERROR", message)
                if quote:
                    if has_client_booking_overlap("public", customer.phone, starts_at, 120):
                        return error_response(409, "CLIENT_TIME_CONFLICT", "У вас есть пересекающаяся запись")
                    table = choose_table(partner, "public", request.data["party_size"], starts_at, starts_at + HOLD)
                    if not table:
                        return error_response(409, "SLOT_UNAVAILABLE", "Нет свободного столика подходящей вместимости")
                    pricing = calculate_booking_pricing([service], None, starts_at, client_phone=customer.phone)
                    return Response(serialize_quote(partner, service, None, [starts_at], [pricing], table=table))
                booking, message = create_restaurant_booking(profile=partner, tenant="public", service=service, starts_at=starts_at, party_size=request.data.get("party_size"), client_name=client_name, client_phone=customer.phone, source=Booking.Source.MOBILE)
                if message:
                    return error_response(409, "SLOT_UNAVAILABLE", message)
                return Response(serialize_mobile_booking(booking), status=201)
            service = Service.objects.select_for_update().filter(id=service_id, tenant_slug="public", partner_profile=partner, is_active=True).first()
            if service is None:
                return error_response(404, "SERVICE_NOT_FOUND", "Услуга не найдена")
            if service.price is None or service.price < 0:
                return error_response(409, "PRICE_NOT_CONFIGURED", "У предложения нет корректной цены")
            if service.duration_minutes <= 0:
                return error_response(409, "DURATION_NOT_CONFIGURED", "У предложения нет корректной длительности")
            mode = booking_category(service)
            if mode == "carwash" and not request.data.get("vehicle"):
                return error_response(400, "VEHICLE_REQUIRED", "Укажите модель и номер автомобиля", "vehicle")
            if mode != "carwash" and request.data.get("vehicle"):
                return error_response(400, "VEHICLE_NOT_SUPPORTED", "Автомобиль допустим только для автомойки", "vehicle")
            attendee_data = request.data.get("attendee", {"type": "self"})
            if attendee_data.get("type") == "child":
                child = customer.children.filter(id=attendee_data.get("child_id")).first()
                if child is None:
                    return error_response(400, "ATTENDEE_UNAVAILABLE", "Ребёнок недоступен", "attendee")
                attendee_data = {**attendee_data, "date_of_birth": child.date_of_birth.isoformat()}
                client_name = child.name
            eligibility = attendee_eligibility_error(service, attendee_data, starts_at)
            if eligibility is not None:
                return eligibility
            if mode in {"photo_studio", "recreation"}:
                if request.data.get("specialist_id") or request.data.get("group_session_id") or request.data.get("visits"):
                    return error_response(400, "RESOURCE_FIELDS", "Для ресурса не передавайте специалиста, группу или посещения")
                if service.is_pass or service.service_type != "individual":
                    return error_response(409, "RESOURCE_SERVICE_UNSUPPORTED", "Для ресурса требуется индивидуальное предложение")
                resource = BookingResource.objects.select_for_update().filter(id=request.data.get("resource_id"), partner=partner, services=service, is_active=True).first()
                if not resource:
                    return error_response(404, "RESOURCE_NOT_FOUND", "Выберите доступный зал или объект", "resource_id")
                if resource.kind != ("hall" if mode == "photo_studio" else "unit"):
                    return error_response(400, "RESOURCE_TYPE_MISMATCH", "Неверный тип ресурса", "resource_id")
                guests = request.data.get("party_size", 1)
                if party_size_error(guests) or guests > resource.capacity:
                    return error_response(400, "RESOURCE_CAPACITY", "Количество гостей превышает вместимость", "party_size")
                message = slot_error([service], starts_at, default=30) or resource_error(resource, starts_at, service.duration_minutes)
                if message:
                    return error_response(409, "SLOT_UNAVAILABLE", message, "starts_at")
                if has_client_booking_overlap("public", customer.phone, starts_at, service.duration_minutes, customer_id=customer.id, attendee=attendee_context):
                    return error_response(409, "CLIENT_TIME_CONFLICT", "У вас уже есть пересекающаяся запись", "starts_at")
                pricing = calculate_booking_pricing([service], None, starts_at, client_phone=customer.phone)
                if quote:
                    return Response(serialize_quote(partner, service, None, [starts_at], [pricing], resource=resource))
                booking = Booking.objects.create(tenant_slug="public", partner_profile=partner, service_name=service.name,
                                                 manager_name=None, starts_at=starts_at, party_size=guests, client_name=client_name,
                                                 client_phone=customer.phone, status="booked", booking_source=Booking.Source.MOBILE, **pricing)
                return Response(serialize_mobile_booking(booking), status=201)
            if request.data.get("resource_id"):
                return error_response(400, "RESOURCE_NOT_SUPPORTED", "Эта услуга не использует зал или объект", "resource_id")
            try:
                specialist_id = int(request.data.get("specialist_id") or "")
            except (TypeError, ValueError):
                return error_response(400, "VALIDATION_ERROR", "Для этой услуги выберите специалиста", "specialist_id")
            specialist = (
                Specialist.objects.select_for_update()
                .filter(
                    id=specialist_id,
                    tenant_slug="public",
                    partner_profile=partner,
                    is_active=True,
                )
                .first()
            )
            if specialist is None:
                return error_response(404, "SPECIALIST_NOT_FOUND", "Специалист не найден")
            service = (
                Service.objects.select_for_update()
                .filter(
                    id=service_id,
                    tenant_slug="public",
                    partner_profile=partner,
                    is_active=True,
                )
                .first()
            )
            if service is None:
                return error_response(404, "SERVICE_NOT_FOUND", "Услуга не найдена")
            message = slot_error([service], starts_at, default=30)
            if message:
                return error_response(400, "VALIDATION_ERROR", message, "starts_at")
            if not specialist.capabilities.filter(service_id=service.id).exists():
                return error_response(409, "SERVICE_UNAVAILABLE", "Специалист не оказывает выбранную услугу")

            group_error = group_booking_error([service])
            if group_error:
                return error_response(409, "SERVICE_UNAVAILABLE", group_error)
            session = None
            if request.data.get("group_session_id"):
                from partner_api.models import GroupSession
                session = GroupSession.objects.select_for_update().select_related("group").filter(
                    id=request.data["group_session_id"], group__partner_profile=partner, group__service=service,
                    group__specialist=specialist, starts_at=starts_at, status="scheduled",
                ).first()
                if not session or service.service_type != "group":
                    return error_response(409, "CLASS_NOT_SCHEDULED", "Занятие недоступно", "group_session_id")
                service = copy(service)
                service.duration_minutes = session.group.duration_minutes
                service.price = session.group.price if service.is_pass else session.base_price
                if service.is_pass and service.pass_price_mode != session.group.price_mode:
                    return error_response(409, "PASS_PRICE_MODE_CHANGED", "Формат цены группы и абонемента не совпадает")
            elif service.service_type == "group" and (service.details or {}).get("require_occurrence"):
                return error_response(400, "CLASS_REQUIRED", "Выберите существующее занятие группы", "group_session_id")

            if service.is_pass:
                raw_visits = request.data.get("visits")
                try:
                    request_id = uuid.uuid5(uuid.NAMESPACE_URL, f"mobile:{customer.id}:{uuid.UUID(str(request.data.get('request_id', '')))}")
                except (ValueError, TypeError, AttributeError):
                    return error_response(400, "VALIDATION_ERROR", "Для абонемента нужен request_id в формате UUID", "request_id")
                if not isinstance(raw_visits, list) or not raw_visits or len(raw_visits) > 365:
                    return error_response(400, "VALIDATION_ERROR", "Выберите даты всех посещений", "visits")
                visits = []
                for raw_visit in raw_visits:
                    try:
                        visit = parse_datetime(raw_visit) if isinstance(raw_visit, str) else None
                    except ValueError:
                        visit = None
                    if visit is None:
                        return error_response(400, "VALIDATION_ERROR", "Дата посещения должна быть в ISO формате", "visits")
                    visit = to_aware_datetime(visit)
                    if timezone.localdate(visit) > timezone.localdate() + timedelta(days=365):
                        return error_response(400, "BOOKING_HORIZON", "Запись доступна на 365 дней вперёд", "visits")
                    message = slot_error([service], visit, default=30)
                    if message:
                        return error_response(400, "VALIDATION_ERROR", message, "visits")
                    visits.append(visit)
                visits.sort()
                for visit in visits:
                    eligibility = attendee_eligibility_error(service, attendee_data, visit)
                    if eligibility is not None:
                        return eligibility
                if session and any(not session.group.sessions.filter(starts_at=visit, status="scheduled").exists() for visit in visits):
                    return error_response(409, "CLASS_NOT_SCHEDULED", "Одна из дат отсутствует в расписании группы", "visits")
                if session:
                    for visit in visits:
                        target = session.group.sessions.get(starts_at=visit, status="scheduled")
                        if has_booking_overlap(specialist.tenant_slug, specialist.full_name, visit, service.duration_minutes,
                                               partner_profile=partner, service=service, specialist_id=specialist.id,
                                               group_session_id=target.id):
                            return error_response(409, "SLOT_UNAVAILABLE", "Занятие занято или нет свободных мест", "visits")
                if visits[0] != starts_at:
                    return error_response(400, "VALIDATION_ERROR", "starts_at должен совпадать с первым посещением", "starts_at")
                payload = {"tenant": specialist.tenant_slug, "source": Booking.Source.MOBILE, "service_id": service.id, "specialist_id": specialist.id, "client_name": client_name, "client_phone": customer.phone, "visits": [value.isoformat() for value in visits]}
                previous = BookingPass.objects.filter(partner_profile=partner, request_id=request_id).first()
                if previous:
                    if quote:
                        return error_response(409, "ALREADY_CREATED", "Абонемент уже создан; используйте поиск по request_id")
                    if previous.request_payload != payload:
                        return error_response(409, "REQUEST_CONFLICT", "request_id уже использован для другого абонемента")
                    return Response(serialize_mobile_booking(previous.bookings.order_by("visit_number").first()))
                message = pass_visits_error(specialist.tenant_slug, partner, service, specialist, visits, "")
                if message:
                    return error_response(409, "SLOT_UNAVAILABLE", message, "visits")
                if any(has_client_booking_overlap(specialist.tenant_slug, customer.phone, visit, service.duration_minutes, customer_id=customer.id, attendee=attendee_context) for visit in visits):
                    return error_response(409, "CLIENT_TIME_CONFLICT", "Одно из посещений пересекается с вашей записью у другого партнёра", "visits")
                if quote:
                    _, pricings = pass_booking_pricing(service, specialist, visits, customer.phone, Booking.Source.MOBILE)
                    return Response(serialize_quote(partner, service, specialist, visits, pricings))
                booking_pass = save_booking_pass(profile=partner, tenant=specialist.tenant_slug, service=service, specialist=specialist, starts=visits, name=client_name, phone=customer.phone, request_id=request_id, payload=payload, source=Booking.Source.MOBILE)
                if session:
                    booking_pass.group = session.group
                    booking_pass.save(update_fields=["group"])
                    for visit_booking in booking_pass.bookings.all():
                        target = session.group.sessions.get(starts_at=visit_booking.starts_at, status="scheduled")
                        visit_booking.group_session = target
                        visit_booking.original_session = target
                        visit_booking.save(update_fields=["group_session", "original_session"])
                return Response(serialize_mobile_booking(booking_pass.bookings.order_by("visit_number").first()), status=201)
            if "visits" in request.data:
                return error_response(400, "VALIDATION_ERROR", "Несколько посещений доступны только для абонемента", "visits")

            duration_minutes = service.duration_minutes or 60
            schedule_error = booking_schedule_error(specialist, starts_at, duration_minutes)
            if schedule_error:
                return error_response(409, "SLOT_UNAVAILABLE", schedule_error, "starts_at")
            if has_booking_overlap(
                specialist.tenant_slug,
                specialist.full_name,
                starts_at,
                duration_minutes,
                partner_profile=partner,
                service=service,
                specialist_id=specialist.id,
                group_session_id=session.id if session else None,
            ):
                return error_response(409, "SLOT_UNAVAILABLE", "У специалиста уже есть запись на это время", "starts_at")
            if has_client_booking_overlap(specialist.tenant_slug, customer.phone, starts_at, duration_minutes, customer_id=customer.id, attendee=attendee_context):
                return error_response(409, "CLIENT_TIME_CONFLICT", "У вас уже есть пересекающаяся запись", "starts_at")

            pricing = calculate_booking_pricing([service], specialist, starts_at, client_phone=customer.phone, allow_discount=True)
            if quote:
                return Response(serialize_quote(partner, service, specialist, [starts_at], [pricing]))
            booking = Booking.objects.create(
                tenant_slug=specialist.tenant_slug,
                partner_profile=partner,
                service_name=service.name,
                manager_name=specialist.full_name,
                starts_at=starts_at,
                client_name=client_name,
                client_phone=customer.phone,
                status="booked",
                booking_source=Booking.Source.MOBILE,
                **pricing,
            )
            attach_group_session(booking, service, specialist)
            if session:
                booking.group_session = session
                booking.original_session = session
                booking.save(update_fields=["group_session", "original_session"])

        return Response(serialize_mobile_booking(booking), status=201)


class MobileBookingQuoteView(MobileBookingsView):
    http_method_names = ["post", "options"]
    @extend_schema(tags=["4. Каталог и запись"], auth=[{"MobileBearer": []}],
                   summary="Рассчитать цену и проверить доступность без резервирования",
                   request=MobileBookingCreateRequestSerializer, responses={200: BookingQuoteSerializer, 400: None, 401: None, 404: None, 409: None})
    def post(self, request):
        serializer = MobileBookingCreateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_response(serializer.errors)
        data = serializer.validated_data
        unknown = set(request.data) - set(serializer.fields)
        if unknown:
            return error_response(400, "UNSUPPORTED_FIELD", "Поле не поддерживается", sorted(unknown)[0])
        if data.get("entries"):
            return error_response(400, "QUOTE_ENTRIES_SEPARATELY", "Запросите расчёт каждой услуги отдельно; создание entries атомарно")
        if "service_id" not in data or "starts_at" not in data:
            return error_response(400, "VALIDATION_ERROR", "Укажите service_id и starts_at")
        attendee = data.get("attendee", {"type": "self"})
        if attendee["type"] == "child":
            child = self.customer.children.filter(id=attendee.get("child_id")).first()
            if not child or serialize_child(child)["age"] >= 18:
                return error_response(400, "ATTENDEE_UNAVAILABLE", "Ребёнок недоступен", "attendee")
        elif attendee.get("child_id"):
            return error_response(400, "VALIDATION_ERROR", "child_id допустим только для ребёнка", "attendee")
        return self._create(SimpleNamespace(data=json.loads(json.dumps(data, default=str))), quote=True)


class MobileBookingCancelView(MobileAuthenticatedView):
    @extend_schema(
        tags=["4. Каталог и запись"],
        auth=[{"MobileBearer": []}],
        summary="Отменить мою запись",
        request=None,
        description="Отменяет будущую активную запись авторизованного клиента. Повторный вызов для уже отменённой записи безопасен и возвращает её текущее состояние.",
        responses={200: MobileBookingSerializer, 401: None, 404: None, 409: None},
    )
    def post(self, request, booking_id: int):
        with transaction.atomic():
            booking = (
                owned_bookings(self.customer).select_for_update(of=("self",))
                .select_related("partner_profile__user")
                .filter(id=booking_id)
                .first()
            )
            if booking is None:
                return error_response(404, "BOOKING_NOT_FOUND", "Запись не найдена")

            status = (booking.status or "").strip().lower()
            if status in {"cancelled", "canceled", "отменен", "отменена"}:
                return Response(serialize_mobile_booking(booking))
            if status in CLOSED_BOOKING_STATUSES:
                return error_response(409, "BOOKING_CANNOT_BE_CANCELLED", "Эту запись уже нельзя отменить")
            if not is_mobile_booking_cancellable(booking):
                return error_response(409, "BOOKING_CANNOT_BE_CANCELLED", "Нельзя отменить начавшуюся или прошедшую запись")

            booking.status = "cancelled"
            booking.save(update_fields=["status"])

        return Response(serialize_mobile_booking(booking))


class MobileAuthSendCodeView(MobileAPIView):
    throttle_scope = "mobile_otp_send"
    @extend_schema(
        tags=['1. Регистрация и вход'],
        summary='Шаг 1. Запросить одноразовый SMS-код',
        description=(
            'Передайте номер телефона. Сервер отправляет одноразовый код на этот номер. '
            'Код не возвращается в API-ответе, действует ограниченное время и используется '
            'на следующем шаге регистрации или входа.'
        ),
        request=SendCodeRequestSerializer,
        responses={200: SendCodeResponseSerializer, 400: None, 429: None, 503: None},
    )
    @transaction.atomic
    def post(self, request):
        phone = normalize_ru_phone(str(request.data.get("phone") or ""))
        if not PHONE_RE.fullmatch(phone):
            return error_response(400, "VALIDATION_ERROR", "Неверный формат номера", "phone")
        challenge, error = send_challenge(phone)
        if error:
            return challenge_error(error)
        return Response({"message": "Development challenge created" if settings.MOBILE_OTP_MODE == "test" else "Code sent",
                         "delivery_mode": settings.MOBILE_OTP_MODE, "expires_in": settings.MOBILE_OTP_TTL_SECONDS,
                         "retry_after": settings.MOBILE_OTP_RESEND_SECONDS, "challenge_id": str(challenge.id)})


class MobileAuthVerifyCodeView(MobileAPIView):
    throttle_scope = "mobile_otp_verify"
    @extend_schema(
        tags=['1. Регистрация и вход'],
        summary='Шаг 2. Войти или создать аккаунт по одноразовому коду',
        description=(
            'После send-code один endpoint обслуживает новые и существующие номера. '
            'Возвращает HTTP200, user, tokens и is_new_user. Согласие не устанавливается автоматически. '
            'Код ограничен по сроку, числу попыток и используется один раз.'
        ),
        request=VerifyCodeRequestSerializer,
        responses={200: AuthenticationResponseSerializer, 400: None, 401: None, 409: None, 429: None, 503: None},
    )
    @transaction.atomic
    def post(self, request):
        serializer = VerifyCodeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_response(serializer.errors)
        phone = normalize_ru_phone(str(request.data.get("phone") or ""))
        code = str(request.data.get("code") or "").strip()
        if not PHONE_RE.fullmatch(phone):
            return error_response(400, "VALIDATION_ERROR", "Неверный формат номера", "phone")
        if not re.fullmatch(rf"[0-9]{{{settings.MOBILE_OTP_LENGTH}}}", code):
            return error_response(400, "VALIDATION_ERROR", "Неверный формат кода", "code")
        customer = CustomerProfile.objects.select_for_update(of=("self",), no_key=True).select_related("user").filter(phone=phone).first()
        _, error = verify_challenge(phone, code)
        if error:
            return challenge_error(error)
        is_new = customer is None
        if is_new:
            try:
                customer = create_mobile_customer(phone, get_request_language(request))
            except IntegrityError:
                if not CustomerProfile.objects.filter(phone=phone).exists():
                    raise
                return error_response(409, "ACCOUNT_CONFLICT", "Номер был привязан другим запросом; запросите новый код")
            from .booking_contract import claim_unowned_bookings
            claim_unowned_bookings(customer)
        if not customer.user.is_active:
            return error_response(401, "ACCOUNT_DISABLED", "Аккаунт недоступен")
        return Response({"user": serialize_customer(customer, request), "tokens": issue_tokens(customer), "is_new_user": is_new})


class MobileAuthRegisterView(MobileAPIView):
    throttle_scope = "mobile_otp_verify"
    @extend_schema(
        tags=['1. Регистрация и вход'],
        summary='Шаг 3A. Создать нового клиента',
        description=(
            'Используйте после шага 1 только для нового номера. API сверяет одноразовый SMS-код, '
            'создаёт профиль клиента и возвращает JWT-токены. После ответа с `is_new_user: true` '
            'вызовите `PATCH /users/me/`, чтобы заполнить имя и город. '
            'Это совместимый endpoint регистрации; для единого входа используйте verify-code.'
        ),
        request=VerifyCodeRequestSerializer,
        responses={201: AuthenticationResponseSerializer, 400: None, 401: None, 409: None, 429: None, 503: None},
    )
    @transaction.atomic
    def post(self, request):
        serializer = VerifyCodeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_response(serializer.errors)
        phone = normalize_ru_phone(str(request.data.get("phone") or ""))
        code = str(request.data.get("code") or "").strip()
        if not PHONE_RE.fullmatch(phone):
            return error_response(400, "VALIDATION_ERROR", "Неверный формат номера", "phone")
        if not re.fullmatch(rf"[0-9]{{{settings.MOBILE_OTP_LENGTH}}}", code):
            return error_response(400, "VALIDATION_ERROR", "Неверный формат кода", "code")
        if CustomerProfile.objects.filter(phone=phone).exists():
            return error_response(409, "USER_ALREADY_EXISTS", "Клиент с этим номером уже зарегистрирован", "phone")
        _, error = verify_challenge(phone, code)
        if error:
            return challenge_error(error)

        try:
            customer = create_mobile_customer(phone, get_request_language(request))
        except IntegrityError:
            if not CustomerProfile.objects.filter(phone=phone).exists():
                raise
            return error_response(409, "USER_ALREADY_EXISTS", "Номер уже используется")
        from .booking_contract import claim_unowned_bookings
        claim_unowned_bookings(customer)
        return Response({"user": serialize_customer(customer, request), "tokens": issue_tokens(customer), "is_new_user": True}, status=201)


class MobileAuthRefreshView(MobileAPIView):
    @extend_schema(
        tags=['2. Сессия'],
        summary='Обновить JWT-токены без SMS',
        description=(
            'Вызывайте при истечении access token или при старте приложения. '
            'Передайте сохранённый refresh token. При успехе сохраните оба токена из ответа: '
            'старый refresh token становится недействительным.'
        ),
        request=RefreshTokenRequestSerializer,
        responses={200: RefreshTokenResponseSerializer, 401: None},
    )
    @transaction.atomic
    def post(self, request):
        payload = decode_token(str(request.data.get("refresh_token") or ""), "refresh")
        if not payload:
            return error_response(401, "INVALID_TOKEN", "refresh token недействителен или просрочен")
        customer = CustomerProfile.objects.select_for_update(of=("self",), no_key=True).filter(id=payload.get("sub"), user__is_active=True).first()
        session = MobileRefreshSession.objects.select_for_update().select_related("customer__user").filter(customer=customer, token_id=payload.get("jti")).first() if customer else None
        if not session or session.revoked_at or session.expires_at <= timezone.now():
            return error_response(401, "INVALID_TOKEN", "refresh token недействителен или просрочен")
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])
        tokens = issue_tokens(session.customer)
        new_session = MobileRefreshSession.objects.get(token_id=decode_token(tokens["access_token"], "access")["jti"])
        session.push_devices.update(session=new_session)
        session.mobiledeletionreceipt_set.filter(completed_at__isnull=True).update(session=new_session)
        return Response({"tokens": tokens})


class MobileAuthLogoutView(MobileAuthenticatedView):
    @extend_schema(tags=["2. Сессия"], auth=[{"MobileBearer": []}],
                   request=LogoutRequestSerializer,
                   summary="Завершить сессию без удаления аккаунта", responses={204: None, 400: None, 401: None})
    @transaction.atomic
    def post(self, request):
        all_devices = request.data.get("all_devices", False)
        if type(all_devices) is not bool:
            return error_response(400, "VALIDATION_ERROR", "all_devices должен быть boolean", "all_devices")
        CustomerProfile.objects.select_for_update(of=("self",), no_key=True).get(id=self.customer.id)
        sessions = MobileRefreshSession.objects.filter(customer=self.customer, revoked_at__isnull=True)
        if not all_devices:
            sessions = sessions.filter(id=self.mobile_session.id)
        self.customer.push_devices.filter(session__in=sessions).update(is_active=False)
        sessions.update(revoked_at=timezone.now())
        return Response(status=204)


class MobileCurrentUserView(MobileAuthenticatedView):
    @extend_schema(
        tags=['3. Профиль клиента'],
        summary='Получить профиль текущего клиента',
        description='Возвращает только профиль клиента, которому принадлежит access token. Идентификатор в URL не нужен.',
        auth=[{'MobileBearer': []}],
        responses={200: CustomerResponseSerializer, 401: None},
    )
    def get(self, request):
        return Response(serialize_customer(self.customer, request))

    @extend_schema(
        tags=['3. Профиль клиента'],
        summary='Заполнить или изменить профиль текущего клиента',
        description=(
            'Для первого заполнения профиля после регистрации передайте как минимум `name` и `city_id`. '
            'Сначала получите допустимые ID через `GET /cities/`. Поле `children` содержит полный '
            'актуальный список детей: новые передавайте без `id`, существующие с `id`; отсутствующие '
            'в массиве дети удаляются. Передавайте не более двух детей.'
        ),
        auth=[{'MobileBearer': []}],
        request=CustomerUpdateRequestSerializer,
        responses={200: CustomerResponseSerializer, 400: None, 401: None},
    )
    def patch(self, request):
        serializer = CustomerUpdateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_response(serializer.errors)
        unknown = set(request.data) - set(serializer.fields)
        if unknown:
            return error_response(400, "UNSUPPORTED_FIELD", "Поле не поддерживается", sorted(unknown)[0])
        data = serializer.validated_data
        customer = self.customer
        user = customer.user
        previous_avatar = customer.avatar_url
        if data.get("revision") and data["revision"] != serialize_customer(customer, request)["revision"]:
            return error_response(409, "STALE_PROFILE", "Профиль изменился; перечитайте его", "revision")
        if "name" in data:
            name = data["name"].strip()
            if not 2 <= len(name) <= 100:
                return error_response(400, "VALIDATION_ERROR", "Имя должно содержать от 2 до 100 символов", "name")
            user.first_name = name
        if "email" in data:
            email = data["email"].strip().lower()
            if email and ("@" not in email or len(email) > 254):
                return error_response(400, "VALIDATION_ERROR", "Некорректный email", "email")
            user.email = email
        if "avatar_url" in data:
            avatar_url = data["avatar_url"].strip()
            if avatar_url and not avatar_url.startswith(("http://", "https://")):
                return error_response(400, "VALIDATION_ERROR", "Некорректный URL фотографии", "avatar_url")
            path = urlsplit(avatar_url).path
            if path.startswith(AVATAR_URL_PREFIX):
                file_name = path.removeprefix(AVATAR_URL_PREFIX)
                if not re.fullmatch(rf"customer-{customer.id}-[a-f0-9]{{32}}\.webp", file_name):
                    return error_response(400, "AVATAR_NOT_OWNED", "Фотография не принадлежит аккаунту", "avatar_url")
                if not (Path(settings.MEDIA_ROOT) / "customer_avatars" / file_name).is_file():
                    return error_response(400, "AVATAR_NOT_FOUND", "Фотография не найдена", "avatar_url")
                avatar_url = path
            customer.avatar_url = avatar_url
        if "city_id" in data:
            city = City.objects.filter(id=data["city_id"], is_active=True).first()
            if not city:
                return error_response(400, "VALIDATION_ERROR", "Город не найден", "city_id")
            customer.city = city
        if "language" in data:
            language = data["language"]
            if language not in {"ru", "kk", "en"}:
                return error_response(400, "VALIDATION_ERROR", "Поддерживаются языки ru, kk, en", "language")
            customer.language = language
        if "agreement_accepted" in data:
            customer.agreement_accepted = data["agreement_accepted"]
        if "agreement_version" in data:
            customer.agreement_version = data["agreement_version"]

        children_data = data.get("children")
        if children_data is not None:
            if not isinstance(children_data, list):
                return error_response(400, "VALIDATION_ERROR", "Дети должны передаваться массивом", "children")
            if len(children_data) > MAX_CHILDREN:
                return error_response(422, "MAX_CHILDREN_REACHED", "Можно указать не более 2 детей", "children")

            existing_children = {child.id: child for child in customer.children.all()}
            requested_child_ids = set()
            children_to_save = []
            today = timezone.localdate()
            for child_data in children_data:
                if not isinstance(child_data, dict):
                    return error_response(400, "VALIDATION_ERROR", "Данные ребёнка должны быть объектом", "children")
                child_id = child_data.get("id")
                if child_id is not None:
                    if not isinstance(child_id, int) or child_id not in existing_children or child_id in requested_child_ids:
                        return error_response(400, "VALIDATION_ERROR", "Некорректный ID ребёнка", "children")
                    child = existing_children[child_id]
                    requested_child_ids.add(child_id)
                else:
                    child = CustomerChild(customer=customer)
                name = str(child_data.get("name") or "").strip()
                if not 1 <= len(name) <= 50 or not all(char.isalpha() or char in " -'’" for char in name) or not any(char.isalpha() for char in name):
                    return error_response(400, "VALIDATION_ERROR", "Имя ребёнка должно содержать от 1 до 50 букв", "children")
                try:
                    date_of_birth = child_data["date_of_birth"]
                except ValueError:
                    return error_response(400, "VALIDATION_ERROR", "Дата ребёнка должна быть в формате YYYY-MM-DD", "children")
                age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
                if date_of_birth > today or age >= 18:
                    return error_response(422, "INVALID_DATE", "Возраст ребёнка должен быть от 0 до 18 лет", "children")
                child.name = name
                child.date_of_birth = date_of_birth
                children_to_save.append(child)

            with transaction.atomic():
                user.save()
                customer.save()
                customer.children.exclude(id__in=requested_child_ids).delete()
                for child in children_to_save:
                    child.save()
        else:
            user.save()
            customer.save()
        if previous_avatar != customer.avatar_url:
            transaction.on_commit(lambda: delete_stored_avatar(previous_avatar))
        return Response(serialize_customer(customer, request))

    @extend_schema(
        tags=['3. Профиль клиента'], summary='Удалить аккаунт текущего клиента', auth=[{'MobileBearer': []}],
        parameters=[OpenApiParameter(
            "X-Deletion-Receipt", str, OpenApiParameter.HEADER,
            description="Optional private receipt from deletion-request; save it before DELETE to reconcile a lost response.",
        )],
        responses={204: None, 401: None, 409: None},
    )
    def delete(self, request):
        from .models import MobileDeletionReceipt
        from .booking_contract import claim_unowned_bookings
        from .release_views import deletion_receipt
        raw_receipt = request.headers.get("X-Deletion-Receipt")
        if raw_receipt is not None:
            receipt = deletion_receipt(raw_receipt)
            if (receipt is None or receipt.customer_id != self.customer.id
                    or receipt.session_id != self.mobile_session.id or receipt.completed_at):
                return error_response(409, "INVALID_DELETION_RECEIPT", "Deletion receipt is invalid for this session")
        claim_unowned_bookings(self.customer)
        MobileDeletionReceipt.objects.filter(customer=self.customer, completed_at__isnull=True).update(completed_at=timezone.now())
        MobileRefreshSession.objects.filter(customer=self.customer).update(revoked_at=timezone.now())
        previous_avatar = self.customer.avatar_url
        self.customer.user.delete()
        transaction.on_commit(lambda: delete_stored_avatar(previous_avatar))
        return Response(status=204)


class MobileCurrentUserAvatarView(MobileAuthenticatedView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=['3. Профиль клиента'],
        summary='Загрузить или заменить фотографию клиента',
        description='Передайте файл в поле `file` как `multipart/form-data`. Допускаются изображения до 5 MB; сервер уменьшает их и сохраняет в WebP.',
        auth=[{'MobileBearer': []}],
        request=AvatarUploadRequestSerializer,
        responses={200: AvatarUploadResponseSerializer, 400: None, 401: None, 413: None, 415: None},
    )
    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return error_response(400, "VALIDATION_ERROR", "Передайте изображение в поле file", "file")
        if uploaded_file.size > MAX_AVATAR_SIZE_BYTES:
            return error_response(413, "IMAGE_TOO_LARGE", "Максимальный размер: 5242880 байт", "file")

        avatar_url, error = save_customer_avatar(uploaded_file, self.customer.id)
        if error:
            return error_response(400, "INVALID_IMAGE", error, "file")

        previous_avatar_url = self.customer.avatar_url
        self.customer.avatar_url = avatar_url
        try:
            self.customer.save(update_fields=["avatar_url", "updated_at"])
        except DatabaseError:
            delete_stored_avatar(avatar_url)
            raise
        transaction.on_commit(lambda: delete_stored_avatar(previous_avatar_url))
        return Response({"avatar_url": request.build_absolute_uri(avatar_url)})


class MobileAvatarImageView(MobileAPIView):
    @extend_schema(exclude=True)
    def get(self, request, filename):
        if not re.fullmatch(r"customer-[0-9]+-[a-f0-9]{32}\.webp", filename):
            raise Http404
        path = Path(settings.MEDIA_ROOT) / "customer_avatars" / filename
        if not path.is_file():
            raise Http404
        response = FileResponse(path.open("rb"), content_type="image/webp")
        response["Cache-Control"] = "public, max-age=31536000, immutable"
        response["X-Content-Type-Options"] = "nosniff"
        return response