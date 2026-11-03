from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.hashers import check_password
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from common_api.views import normalize_ru_phone
from partner_api.models import Booking, Service, Specialist
from partner_api.views import (
    booking_schedule_error, calculate_booking_pricing, has_booking_overlap,
    has_client_booking_overlap, group_booking_error,
)
from partner_api.intervals import slot_error
from partner_api.restaurant import choose_table, HOLD
from .catalog_contract import resource_error
from .booking_contract import booking_identity, booking_revision, claim_unowned_bookings, owned_bookings, status_group
from .models import (
    BookingReview, CustomerProfile, Favorite, MobileBookingRecord, MobileBookingRequest,
    MobileContent, MobileNotification, MobileRefreshSession, NotificationPreferences, PhoneChallenge,
)
from .otp import send_challenge, verify_challenge
from .serializers import (
    BookingReviewSerializer, CatalogPartnerSerializer, CustomerResponseSerializer,
    MobileBookingSerializer, RescheduleRequestSerializer, ReviewRequestSerializer,
    SendCodeRequestSerializer, SendCodeResponseSerializer, VerifyCodeRequestSerializer,
)
from .views import (
    PHONE_RE, MobileAuthenticatedView, active_catalog_partners, challenge_error,
    MobileAPIView,
    error_response, serialize_catalog_partner, serialize_customer, serialize_mobile_booking,
    validation_response,
)


def validate(serializer):
    unknown = set(serializer.initial_data) - set(serializer.fields)
    if unknown:
        return error_response(400, "UNSUPPORTED_FIELD", "Поле не поддерживается", sorted(unknown)[0])
    if serializer.is_valid():
        return None
    return validation_response(serializer.errors)


def review_data(review, public=False):
    data = {"id": review.id, "booking_id": review.booking_id, "rating": review.rating,
            "comment": review.comment, "language": review.language,
            "state": review.state, "created_at": review.created_at.isoformat()}
    if public:
        data.pop("booking_id")
        data["author_display_name"] = "Клиент"
    return data


def page(request, query):
    try:
        limit = int(request.query_params.get("limit", "20"))
    except (TypeError, ValueError):
        return None, error_response(400, "INVALID_PAGE", "limit должен быть числом", "limit")
    if not 1 <= limit <= 100:
        return None, error_response(400, "INVALID_PAGE", "limit должен быть от 1 до 100", "limit")
    oldest = request.query_params.get("order", "newest") == "oldest"
    if request.query_params.get("order", "newest") not in {"newest", "oldest"}:
        return None, error_response(400, "INVALID_PAGE", "order должен быть newest или oldest", "order")
    cursor = request.query_params.get("cursor")
    if cursor:
        try:
            position = signing.loads(cursor, salt="mobile-feed")
            instant = parse_datetime(position["created_at"])
            identity = int(position["id"])
            if instant is None or position["oldest"] != oldest:
                raise ValueError("Invalid cursor")
        except (signing.BadSignature, KeyError, TypeError, ValueError):
            return None, error_response(400, "INVALID_CURSOR", "Некорректный курсор", "cursor")
        if oldest:
            query = query.filter(Q(created_at__gt=instant) | Q(created_at=instant, id__gt=identity))
        else:
            query = query.filter(Q(created_at__lt=instant) | Q(created_at=instant, id__lt=identity))
    prefix = "" if oldest else "-"
    items = list(query.order_by(f"{prefix}created_at", f"{prefix}id")[:limit + 1])
    next_cursor = None
    if len(items) > limit:
        last = items[limit - 1]
        next_cursor = signing.dumps({"created_at": last.created_at.isoformat(), "id": last.id, "oldest": oldest}, salt="mobile-feed")
    return {"items": items[:limit], "next_cursor": next_cursor}, None


class FavoriteListSerializer(serializers.Serializer):
    data = CatalogPartnerSerializer(many=True)
    total = serializers.IntegerField()
    is_complete = serializers.BooleanField()


class MobileFavoritesView(MobileAuthenticatedView):
    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], responses={200: FavoriteListSerializer})
    def get(self, request):
        favorites = self.customer.favorites.filter(partner__user__is_active=True, partner__user_type="partner").select_related("partner__user").order_by("-created_at", "-id")
        data = [serialize_catalog_partner(item.partner, request) for item in favorites]
        return Response({"data": data, "total": len(data), "is_complete": True})

    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], operation_id="mobile_favorites_clear",
                   summary="Атомарно очистить избранное", responses={204: None})
    def delete(self, request):
        self.customer.favorites.all().delete()
        return Response(status=204)


class MobileFavoriteView(MobileAuthenticatedView):
    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], request=None, responses={200: CatalogPartnerSerializer})
    def put(self, request, partner_id):
        partner = active_catalog_partners().filter(id=partner_id).first()
        if not partner:
            return error_response(404, "PARTNER_NOT_FOUND", "Партнёр не найден")
        Favorite.objects.get_or_create(customer=self.customer, partner=partner)
        return Response(serialize_catalog_partner(partner, request))

    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], operation_id="mobile_favorite_remove", responses={204: None})
    def delete(self, request, partner_id):
        Favorite.objects.filter(customer=self.customer, partner_id=partner_id).delete()
        return Response(status=204)


class MobileBookingReviewView(MobileAuthenticatedView):
    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], responses={200: BookingReviewSerializer, 404: None})
    def get(self, request, booking_id):
        review = BookingReview.objects.filter(customer=self.customer, booking_id=booking_id).first()
        return Response(review_data(review)) if review else error_response(404, "REVIEW_NOT_FOUND", "Отзыв не найден")

    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], request=ReviewRequestSerializer,
                   responses={201: BookingReviewSerializer, 200: BookingReviewSerializer, 400: None, 404: None, 409: None})
    def post(self, request, booking_id):
        serializer = ReviewRequestSerializer(data=request.data)
        error = validate(serializer)
        if error is not None:
            return error
        booking = owned_bookings(self.customer).select_for_update(of=("self",)).filter(id=booking_id).first()
        if not booking:
            return error_response(404, "BOOKING_NOT_FOUND", "Запись не найдена")
        data = serializer.validated_data
        previous = BookingReview.objects.filter(booking=booking).first()
        if previous:
            if previous.customer_id != self.customer.id or previous.rating != data["rating"] or previous.comment != data["comment"]:
                return error_response(409, "REVIEW_EXISTS", "Отзыв уже отправлен с другим содержимым")
            return Response(review_data(previous))
        if status_group(booking) != "completed":
            return error_response(409, "REVIEW_NOT_ELIGIBLE", "Отзыв доступен только после завершённого визита")
        review = BookingReview.objects.create(booking=booking, customer=self.customer, language=self.customer.language, **data)
        return Response(review_data(review), status=201)


class PublicReviewSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    rating = serializers.IntegerField()
    comment = serializers.CharField()
    language = serializers.CharField()
    state = serializers.CharField()
    created_at = serializers.DateTimeField()
    author_display_name = serializers.CharField()


class ReviewListSerializer(serializers.Serializer):
    data = PublicReviewSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    total = serializers.IntegerField()
    rating_count = serializers.IntegerField()
    rating = serializers.FloatField(allow_null=True)


class MobilePartnerReviewsView(MobileAPIView):
    @extend_schema(tags=["4. Каталог и запись"], responses={200: ReviewListSerializer},
                   parameters=[OpenApiParameter("language", str), OpenApiParameter("limit", int),
                               OpenApiParameter("cursor", str), OpenApiParameter("order", str)])
    def get(self, request, partner_id):
        if not active_catalog_partners().filter(id=partner_id).exists():
            return error_response(404, "PARTNER_NOT_FOUND", "Партнёр не найден")
        all_reviews = BookingReview.objects.filter(booking__partner_profile_id=partner_id, booking__tenant_slug="public", state="published")
        totals = all_reviews.aggregate(rating=Avg("rating"), count=Count("id"))
        query = all_reviews
        language = request.query_params.get("language")
        if language:
            if language not in {"ru", "kk", "en"}:
                return error_response(400, "VALIDATION_ERROR", "Неизвестный язык", "language")
            query = query.filter(language=language)
        result, error = page(request, query)
        if error is not None:
            return error
        return Response({"data": [review_data(item, public=True) for item in result["items"]],
                         "next_cursor": result["next_cursor"], "total": query.count(),
                         "rating": totals["rating"], "rating_count": totals["count"]})


class MobileBookingRescheduleView(MobileAuthenticatedView):
    @extend_schema(tags=["4. Каталог и запись"], auth=[{"MobileBearer": []}],
                   request=RescheduleRequestSerializer, responses={200: MobileBookingSerializer, 400: None, 404: None, 409: None})
    def post(self, request, booking_id):
        serializer = RescheduleRequestSerializer(data=request.data)
        error = validate(serializer)
        if error is not None:
            return error
        data = serializer.validated_data
        request_id = data["request_id"]
        payload = {key: str(value) for key, value in data.items()}
        payload["booking_id"] = booking_id
        previous = MobileBookingRequest.objects.filter(customer=self.customer, request_id=request_id, operation="reschedule").first()
        if previous and previous.payload != payload:
            return error_response(409, "REQUEST_CONFLICT", "request_id уже использован")
        booking = owned_bookings(self.customer).filter(id=booking_id).first()
        if not booking:
            return error_response(404, "BOOKING_NOT_FOUND", "Запись не найдена")
        partner = active_catalog_partners().select_for_update(of=("self",)).filter(id=booking.partner_profile_id).first()
        if not partner:
            return error_response(409, "PARTNER_UNAVAILABLE", "Партнёр недоступен")
        booking = owned_bookings(self.customer).select_for_update(of=("self",)).filter(id=booking_id).first()
        if not booking:
            return error_response(404, "BOOKING_NOT_FOUND", "Запись не найдена")
        if previous:
            return Response(serialize_mobile_booking(booking))
        if booking_revision(booking) != data["revision"]:
            return error_response(409, "STALE_BOOKING", "Запись изменилась; перечитайте её", "revision")
        if status_group(booking) != "upcoming" or booking.starts_at <= timezone.now():
            return error_response(409, "RESCHEDULE_NOT_ELIGIBLE", "Эту запись нельзя перенести")
        ids, old_specialist_id, duration = booking_identity(booking)
        if len(ids) != 1 or not duration:
            return error_response(409, "BOOKING_DETAILS_REQUIRED", "Для этой старой записи нет однозначных данных услуги")
        service = Service.objects.filter(id=ids[0], partner_profile=partner, tenant_slug=booking.tenant_slug, is_active=True).first()
        if not service:
            return error_response(409, "SERVICE_UNAVAILABLE", "Услуга недоступна")
        if group_booking_error([service]):
            return error_response(409, "SERVICE_UNAVAILABLE", "Формат услуги недоступен")
        start = data["starts_at"]
        if start <= timezone.now() or timezone.localdate(start) > timezone.localdate() + timedelta(days=365):
            return error_response(400, "BOOKING_HORIZON", "Начало должно быть в будущем, не далее 365 дней", "starts_at")
        record = getattr(booking, "mobile_record", None)
        if not booking.table_id:
            from .views import attendee_eligibility_error
            eligibility = attendee_eligibility_error(service, record.attendee if record else {}, start)
            if eligibility is not None:
                return eligibility
        resource = record.resource if record and record.resource_id else None
        if booking.table_id or resource:
            if "specialist_id" in data:
                return error_response(400, "SPECIALIST_NOT_SUPPORTED", "Для столика или объекта специалист не выбирается")
            message = slot_error([service], start, default=30)
            if resource:
                from .models import BookingResource
                original_resource = resource
                resource = BookingResource.objects.select_for_update().filter(id=data.get("resource_id", resource.id), partner=partner, is_active=True, services=service).first()
                if not resource or resource.kind != original_resource.kind or (booking.party_size or 1) > resource.capacity:
                    return error_response(409, "RESOURCE_UNAVAILABLE", "Ресурс недоступен")
                message = message or resource_error(resource, start, duration, exclude_booking_id=booking.id)
            elif "resource_id" in data:
                return error_response(400, "RESOURCE_NOT_SUPPORTED", "Столик назначается автоматически")
            if message:
                return error_response(409, "SLOT_UNAVAILABLE", message, "starts_at")
            if has_client_booking_overlap(booking.tenant_slug, self.customer.phone, start, duration, exclude_booking_id=booking.id, customer_id=self.customer.id, attendee=record.attendee if record else None):
                return error_response(409, "CLIENT_TIME_CONFLICT", "У вас есть пересекающаяся запись")
            table = choose_table(partner, booking.tenant_slug, booking.party_size, start, start + HOLD, exclude_ids=(booking.id,)) if booking.table_id else None
            if booking.table_id and not table:
                return error_response(409, "SLOT_UNAVAILABLE", "Нет свободного столика подходящей вместимости")
            pricing = calculate_booking_pricing([service], None, start, client_phone=self.customer.phone)
            pricing["pricing_details"][0]["duration_minutes"] = duration
            if "expected_final_price" in data and pricing["final_price"] != data["expected_final_price"]:
                return error_response(409, "PRICE_CHANGED", "Цена изменилась", "expected_final_price")
            booking.starts_at = start
            if table:
                booking.table = table
                booking.manager_name = table.name
                booking.ends_at = start + HOLD
            for field, value in pricing.items():
                setattr(booking, field, value)
            booking.save()
            if table:
                from .views import table_booking_snapshot
                MobileBookingRecord.objects.update_or_create(
                    booking=booking, defaults={"customer": self.customer, "owner_claimed": True,
                                              "resource_snapshot": table_booking_snapshot(booking)},
                )
            if resource:
                from .catalog_contract import resource_data
                record.resource = resource
                record.resource_snapshot = {**resource_data(resource), "party_size": booking.party_size}
                record.save(update_fields=["resource", "resource_snapshot"])
            if "comment" in data:
                MobileBookingRecord.objects.filter(booking=booking).update(comment=data["comment"])
            MobileBookingRequest.objects.create(customer=self.customer, request_id=request_id, operation="reschedule", payload=payload, booking_ids=[booking.id])
            booking.refresh_from_db()
            return Response(serialize_mobile_booking(booking))
        specialist = Specialist.objects.select_for_update().filter(
            id=data.get("specialist_id", old_specialist_id), partner_profile=partner, is_active=True, tenant_slug=booking.tenant_slug,
        ).first()
        if not service or not specialist or not specialist.capabilities.filter(service=service).exists():
            return error_response(409, "SERVICE_UNAVAILABLE", "Услуга или специалист недоступны")
        if "resource_id" in data:
            return error_response(400, "RESOURCE_NOT_SUPPORTED", "Эта запись не использует зал или объект")
        from partner_api.models import GroupSession
        target_session = None
        if service.service_type == "group":
            target_session = GroupSession.objects.filter(group__partner_profile=partner, group__tenant_slug=booking.tenant_slug,
                                                        group__service=service, group__specialist=specialist, starts_at=start, status="scheduled").first()
            if not target_session:
                return error_response(409, "CLASS_NOT_SCHEDULED", "Выберите существующее занятие группы")
            duration = target_session.group.duration_minutes
        message = slot_error([service], start, default=30) or booking_schedule_error(specialist, start, duration)
        if message:
            return error_response(409, "SLOT_UNAVAILABLE", message, "starts_at")
        if has_booking_overlap(booking.tenant_slug, specialist.full_name, start, duration, partner_profile=partner, service=service, exclude_booking_id=booking.id, specialist_id=specialist.id, group_session_id=target_session.id if target_session else None):
            return error_response(409, "SLOT_UNAVAILABLE", "Время занято", "starts_at")
        if has_client_booking_overlap(booking.tenant_slug, self.customer.phone, start, duration, exclude_booking_id=booking.id, customer_id=self.customer.id, attendee=record.attendee if record else None):
            return error_response(409, "CLIENT_TIME_CONFLICT", "У вас есть пересекающаяся запись", "starts_at")
        pricing = calculate_booking_pricing([service], specialist, start, client_phone=self.customer.phone)
        pricing["pricing_details"][0]["duration_minutes"] = duration
        if booking.booking_pass_id:
            from decimal import ROUND_HALF_UP
            detail = pricing["pricing_details"][0]
            discount = (booking.base_price * Decimal(detail["discount_percent"]) / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            pricing.update(base_price=booking.base_price, discount_amount=discount, final_price=booking.base_price - discount)
            detail.update(base_price=str(booking.base_price), discount_amount=str(discount), final_price=str(booking.base_price - discount))
        if "expected_final_price" in data and pricing["final_price"] != data["expected_final_price"]:
            return error_response(409, "PRICE_CHANGED", "Цена изменилась", "expected_final_price")
        booking.starts_at = start
        booking.manager_name = specialist.full_name
        booking.group_session = target_session
        booking.is_individual_override = bool(booking.original_session_id and not target_session)
        for field, value in pricing.items():
            setattr(booking, field, value)
        booking.save()
        if "comment" in data:
            MobileBookingRecord.objects.update_or_create(booking=booking, defaults={"comment": data["comment"]})
        MobileBookingRequest.objects.create(customer=self.customer, request_id=request_id, operation="reschedule", payload=payload, booking_ids=[booking.id])
        booking.refresh_from_db()
        return Response(serialize_mobile_booking(booking))


class TotalsSerializer(serializers.Serializer):
    completed_visits = serializers.IntegerField()
    savings = serializers.DecimalField(max_digits=20, decimal_places=2)
    final_price_total = serializers.DecimalField(max_digits=20, decimal_places=2)
    completed_entries = serializers.IntegerField()


class StatisticsSerializer(serializers.Serializer):
    currency = serializers.CharField()
    time_zone = serializers.CharField()
    month = serializers.CharField()
    all_time = TotalsSerializer()
    selected_month = TotalsSerializer()


class MobileBookingStatisticsView(MobileAuthenticatedView):
    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], responses={200: StatisticsSerializer},
                   parameters=[OpenApiParameter("month", str, description="YYYY-MM, Asia/Almaty")])
    def get(self, request):
        month = request.query_params.get("month") or timezone.localdate().strftime("%Y-%m")
        try:
            start_date = date.fromisoformat(f"{month}-01")
            if len(month) != 7:
                raise ValueError("Invalid month")
            end_date = date(start_date.year + (start_date.month == 12), start_date.month % 12 + 1, 1)
        except ValueError:
            return error_response(400, "VALIDATION_ERROR", "month должен быть YYYY-MM", "month")
        start = timezone.make_aware(datetime.combine(start_date, time.min))
        end = timezone.make_aware(datetime.combine(end_date, time.min))
        completed = [item for item in owned_bookings(self.customer).select_related("mobile_record") if status_group(item) == "completed"]
        if any(item.discount_amount < 0 or item.final_price < 0 for item in completed):
            return error_response(409, "INVALID_BOOKING_AMOUNTS", "История содержит некорректные суммы")
        def totals(items):
            visit_ids = {str(item.mobile_record.batch_id) if getattr(item, "mobile_record", None) and item.mobile_record.batch_id else f"booking:{item.id}" for item in items}
            return {"completed_visits": len(visit_ids), "completed_entries": len(items),
                    "savings": str(sum((item.discount_amount for item in items), Decimal("0.00"))),
                    "final_price_total": str(sum((item.final_price for item in items), Decimal("0.00")))}
        return Response({"currency": "KZT", "time_zone": timezone.get_current_timezone_name(), "month": month,
                         "all_time": totals(completed), "selected_month": totals([item for item in completed if start <= item.starts_at < end])})


class NotificationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.CharField()
    booking_id = serializers.IntegerField(allow_null=True)
    parameters = serializers.JSONField()
    created_at = serializers.DateTimeField()
    read_at = serializers.DateTimeField(allow_null=True)


class NotificationListSerializer(serializers.Serializer):
    data = NotificationSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    unread_count = serializers.IntegerField()
    total = serializers.IntegerField()
    time_zone = serializers.CharField()


class MobileNotificationsView(MobileAuthenticatedView):
    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], responses={200: NotificationListSerializer},
                   parameters=[OpenApiParameter("limit", int), OpenApiParameter("cursor", str)])
    def get(self, request):
        query = self.customer.notifications.all()
        result, error = page(request, query)
        if error is not None:
            return error
        return Response({"data": [{"id": item.id, "type": item.type, "booking_id": item.booking_id,
                                  "parameters": item.parameters, "created_at": item.created_at.isoformat(),
                                  "read_at": item.read_at.isoformat() if item.read_at else None} for item in result["items"]],
                         "next_cursor": result["next_cursor"], "unread_count": query.filter(read_at__isnull=True).count(),
                         "total": query.count(), "time_zone": timezone.get_current_timezone_name()})


class UnreadCountSerializer(serializers.Serializer):
    unread_count = serializers.IntegerField()


class MobileNotificationReadView(MobileAuthenticatedView):
    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], request=None, responses={200: UnreadCountSerializer, 404: None})
    def post(self, request, notification_id=None):
        query = self.customer.notifications.all()
        if notification_id is not None:
            query = query.filter(id=notification_id)
            if not query.exists():
                return error_response(404, "NOTIFICATION_NOT_FOUND", "Уведомление не найдено")
        query.filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"unread_count": self.customer.notifications.filter(read_at__isnull=True).count()})


class PreferencesSerializer(serializers.Serializer):
    delivery_enabled = serializers.BooleanField(required=False)
    bookings_enabled = serializers.BooleanField(required=False)
    offers_enabled = serializers.BooleanField(required=False)
    updated_at = serializers.DateTimeField(read_only=True)


class MobileNotificationPreferencesView(MobileAuthenticatedView):
    def result(self, preferences):
        return Response({"delivery_enabled": preferences.delivery_enabled, "bookings_enabled": preferences.bookings_enabled,
                         "offers_enabled": preferences.offers_enabled, "updated_at": preferences.updated_at.isoformat()})

    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], responses={200: PreferencesSerializer})
    def get(self, request):
        preferences, _ = NotificationPreferences.objects.get_or_create(customer=self.customer)
        return self.result(preferences)

    @extend_schema(tags=["5. Аккаунт"], auth=[{"MobileBearer": []}], request=PreferencesSerializer, responses={200: PreferencesSerializer})
    def patch(self, request):
        serializer = PreferencesSerializer(data=request.data)
        error = validate(serializer)
        if error is not None:
            return error
        preferences, _ = NotificationPreferences.objects.get_or_create(customer=self.customer)
        for field, value in serializer.validated_data.items():
            setattr(preferences, field, value)
        preferences.save()
        return self.result(preferences)


class MobilePhoneChangeRequestView(MobileAuthenticatedView):
    throttle_scope = "mobile_otp_send"
    @extend_schema(tags=["3. Профиль клиента"], auth=[{"MobileBearer": []}], request=SendCodeRequestSerializer,
                   responses={200: SendCodeResponseSerializer, 400: None, 409: None, 429: None, 503: None})
    def post(self, request):
        phone = normalize_ru_phone(str(request.data.get("phone") or ""))
        if not PHONE_RE.fullmatch(phone):
            return error_response(400, "VALIDATION_ERROR", "Неверный формат номера", "phone")
        if phone == self.customer.phone:
            return error_response(400, "PHONE_UNCHANGED", "Этот номер уже установлен", "phone")
        if CustomerProfile.objects.filter(phone=phone).exists():
            return error_response(409, "PHONE_IN_USE", "Номер уже используется", "phone")
        challenge, error = send_challenge(phone, purpose="phone_change", customer=self.customer, session_id=self.mobile_session.token_id)
        if error:
            return challenge_error(error)
        from django.conf import settings
        return Response({"message": "Development challenge created" if settings.MOBILE_OTP_MODE == "test" else "Code sent",
                         "delivery_mode": settings.MOBILE_OTP_MODE, "expires_in": settings.MOBILE_OTP_TTL_SECONDS,
                         "retry_after": settings.MOBILE_OTP_RESEND_SECONDS, "challenge_id": str(challenge.id)})


class PhoneChangeResponseSerializer(serializers.Serializer):
    user = CustomerResponseSerializer()
    changed = serializers.BooleanField()


class MobilePhoneChangeConfirmView(MobileAuthenticatedView):
    throttle_scope = "mobile_otp_verify"
    @extend_schema(tags=["3. Профиль клиента"], auth=[{"MobileBearer": []}], request=VerifyCodeRequestSerializer,
                   responses={200: PhoneChangeResponseSerializer, 400: None, 401: None, 409: None})
    def post(self, request):
        phone = normalize_ru_phone(str(request.data.get("phone") or ""))
        code = str(request.data.get("code") or "")
        if not PHONE_RE.fullmatch(phone):
            return error_response(400, "VALIDATION_ERROR", "Неверный формат номера", "phone")
        if phone == self.customer.phone:
            return Response({"user": serialize_customer(self.customer, request), "changed": False})
        if CustomerProfile.objects.filter(phone=phone).exclude(id=self.customer.id).exists():
            return error_response(409, "PHONE_IN_USE", "Номер уже используется", "phone")
        _, error = verify_challenge(phone, code, purpose="phone_change", customer=self.customer, session_id=self.mobile_session.token_id)
        if error:
            return challenge_error(error)
        claim_unowned_bookings(self.customer)
        old_phone = self.customer.phone
        try:
            with transaction.atomic():
                self.customer.phone = phone
                self.customer.save(update_fields=["phone", "updated_at"])
        except IntegrityError:
            return error_response(409, "PHONE_IN_USE", "Номер уже используется", "phone")
        Booking.objects.filter(mobile_record__customer=self.customer).update(client_phone=phone)
        PhoneChallenge.objects.filter(phone=old_phone, purpose="signin", consumed_at__isnull=True).update(consumed_at=timezone.now())
        self.customer.push_devices.exclude(session=self.mobile_session).update(is_active=False)
        MobileRefreshSession.objects.filter(customer=self.customer).exclude(id=self.mobile_session.id).update(revoked_at=timezone.now())
        return Response({"user": serialize_customer(self.customer, request), "changed": True})


class ContentSerializer(serializers.Serializer):
    key = serializers.CharField()
    kind = serializers.CharField()
    language = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField(allow_blank=True)
    url = serializers.URLField(allow_blank=True)
    version = serializers.CharField()
    effective_at = serializers.DateTimeField()


class ContentListSerializer(serializers.Serializer):
    data = ContentSerializer(many=True)
    is_configured = serializers.BooleanField()


class MobileContentView(MobileAPIView):
    @extend_schema(tags=["0. Справочники"], responses={200: ContentListSerializer},
                   parameters=[OpenApiParameter("language", str), OpenApiParameter("kind", str)])
    def get(self, request):
        language = request.query_params.get("language", "ru")
        kind = request.query_params.get("kind")
        if language not in {"ru", "kk", "en"} or (kind and kind not in {"faq", "legal", "support"}):
            return error_response(400, "VALIDATION_ERROR", "Неизвестный язык или тип контента")
        query = MobileContent.objects.filter(language=language, is_published=True, effective_at__lte=timezone.now())
        if kind:
            query = query.filter(kind=kind)
        data = [{"key": item.key, "kind": item.kind, "language": item.language, "title": item.title,
                 "body": item.body, "url": item.url, "version": item.version, "effective_at": item.effective_at.isoformat()}
                for item in query.order_by("display_order", "key")]
        return Response({"data": data, "is_configured": bool(data)})
