import re
import uuid
from datetime import date, timedelta

import jwt
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common_api.views import normalize_ru_phone

from .models import CustomerChild, CustomerProfile, MobileRefreshSession
from .serializers import (
    ChildRequestSerializer,
    CustomerUpdateRequestSerializer,
    RefreshTokenRequestSerializer,
    SendCodeRequestSerializer,
    VerifyCodeRequestSerializer,
)


PHONE_RE = re.compile(r"^\+7\d{10}$")
CHILD_NAME_RE = re.compile(r"^[^\d_]{1,50}$")
MAX_CHILDREN = 2


def error_response(status_code, code, message, field=None):
    details = []
    if field:
        details.append({"field": field, "message": message})
    return Response({"error": {"code": code, "message": message, "details": details}}, status=status_code)


def get_request_language(request):
    language = (request.data.get("language") or request.headers.get("Accept-Language") or "ru").lower()
    return language[:2] if language[:2] in {"ru", "kk", "en"} else "ru"


def serialize_child(child):
    today = timezone.localdate()
    age = today.year - child.date_of_birth.year - (
        (today.month, today.day) < (child.date_of_birth.month, child.date_of_birth.day)
    )
    return {
        "id": str(child.id),
        "name": child.name,
        "date_of_birth": child.date_of_birth.isoformat(),
        "age": age,
    }


def serialize_customer(customer):
    children = list(customer.children.order_by("id"))
    return {
        "id": str(customer.id),
        "phone": customer.phone,
        "name": customer.user.first_name or None,
        "email": customer.user.email or None,
        "avatar_url": customer.avatar_url or None,
        "city_id": customer.city_id or None,
        "city_name": customer.city_name or None,
        "language": customer.language,
        "is_profile_complete": bool(customer.user.first_name and customer.city_id),
        "agreement_accepted": customer.agreement_accepted,
        "agreement_version": customer.agreement_version or None,
        "children": [serialize_child(child) for child in children],
        "max_children": MAX_CHILDREN,
        "created_at": customer.created_at.isoformat(),
        "updated_at": customer.updated_at.isoformat(),
    }


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
        token_payload(customer, "access", access_expires_at),
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
    return payload if payload.get("type") == expected_type else None


class MobileAuthenticatedView(APIView):
    customer = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        auth_header = request.headers.get("Authorization", "")
        scheme, _, raw_token = auth_header.partition(" ")
        payload = decode_token(raw_token, "access") if scheme.lower() == "bearer" else None
        if not payload:
            self.permission_denied(request, message="UNAUTHORIZED")
        self.customer = CustomerProfile.objects.select_related("user").filter(id=payload["sub"]).first()
        if not self.customer:
            self.permission_denied(request, message="UNAUTHORIZED")

    def handle_exception(self, exc):
        if getattr(exc, "detail", None) == "UNAUTHORIZED":
            return error_response(401, "UNAUTHORIZED", "Недействительный access token")
        return super().handle_exception(exc)


class MobileAuthSendCodeView(APIView):
    @extend_schema(
        tags=['Авторизация'],
        summary='Запросить SMS-код',
        request=SendCodeRequestSerializer,
        responses={200: None, 400: None},
    )
    def post(self, request):
        phone = normalize_ru_phone(str(request.data.get("phone") or ""))
        if not PHONE_RE.fullmatch(phone):
            return error_response(400, "VALIDATION_ERROR", "Неверный формат номера", "phone")
        return Response({"message": "Code sent", "expires_in": 120, "retry_after": 120})


class MobileAuthVerifyCodeView(APIView):
    @extend_schema(
        tags=['Авторизация'],
        summary='Подтвердить SMS-код и войти',
        description='В режиме разработки принимается код `11111`.',
        request=VerifyCodeRequestSerializer,
        responses={200: None, 400: None, 401: None},
    )
    def post(self, request):
        phone = normalize_ru_phone(str(request.data.get("phone") or ""))
        code = str(request.data.get("code") or "").strip()
        if not PHONE_RE.fullmatch(phone):
            return error_response(400, "VALIDATION_ERROR", "Неверный формат номера", "phone")
        if not re.fullmatch(r"\d{5}", code):
            return error_response(400, "VALIDATION_ERROR", "Код должен состоять из 5 цифр", "code")
        if code != settings.MOBILE_SMS_TEST_CODE:
            return error_response(401, "INVALID_CODE", "SMS-код неверен")

        customer = CustomerProfile.objects.select_related("user").filter(phone=phone).first()
        is_new_user = customer is None
        if customer is None:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=f"mobile:{phone}",
                    password=None,
                )
                customer = CustomerProfile.objects.create(
                    user=user,
                    phone=phone,
                    language=get_request_language(request),
                )
        return Response({"user": serialize_customer(customer), "tokens": issue_tokens(customer), "is_new_user": is_new_user})


class MobileAuthRefreshView(APIView):
    @extend_schema(
        tags=['Авторизация'],
        summary='Обновить JWT-токены',
        request=RefreshTokenRequestSerializer,
        responses={200: None, 401: None},
    )
    def post(self, request):
        payload = decode_token(str(request.data.get("refresh_token") or ""), "refresh")
        if not payload:
            return error_response(401, "INVALID_TOKEN", "refresh token недействителен или просрочен")
        session = MobileRefreshSession.objects.select_related("customer__user").filter(token_id=payload.get("jti")).first()
        if not session or session.revoked_at or session.expires_at <= timezone.now():
            return error_response(401, "INVALID_TOKEN", "refresh token недействителен или просрочен")
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])
        return Response({"tokens": issue_tokens(session.customer)})


class MobileCurrentUserView(MobileAuthenticatedView):
    @extend_schema(tags=['Клиент'], summary='Получить профиль клиента', auth=['MobileBearer'], responses={200: None, 401: None})
    def get(self, request):
        return Response(serialize_customer(self.customer))

    @extend_schema(
        tags=['Клиент'],
        summary='Изменить профиль клиента',
        auth=['MobileBearer'],
        request=CustomerUpdateRequestSerializer,
        responses={200: None, 400: None, 401: None},
    )
    def patch(self, request):
        customer = self.customer
        user = customer.user
        if "name" in request.data:
            name = str(request.data.get("name") or "").strip()
            if not 2 <= len(name) <= 100:
                return error_response(400, "VALIDATION_ERROR", "Имя должно содержать от 2 до 100 символов", "name")
            user.first_name = name
        if "email" in request.data:
            email = str(request.data.get("email") or "").strip().lower()
            if email and ("@" not in email or len(email) > 254):
                return error_response(400, "VALIDATION_ERROR", "Некорректный email", "email")
            user.email = email
        if "city_id" in request.data:
            customer.city_id = str(request.data.get("city_id") or "").strip()[:80]
        if "city_name" in request.data:
            customer.city_name = str(request.data.get("city_name") or "").strip()[:120]
        if "language" in request.data:
            language = str(request.data.get("language") or "").strip().lower()
            if language not in {"ru", "kk", "en"}:
                return error_response(400, "VALIDATION_ERROR", "Поддерживаются языки ru, kk, en", "language")
            customer.language = language
        user.save()
        customer.save()
        return Response(serialize_customer(customer))

    @extend_schema(tags=['Клиент'], summary='Удалить аккаунт клиента', auth=['MobileBearer'], responses={204: None, 401: None})
    def delete(self, request):
        MobileRefreshSession.objects.filter(customer=self.customer).update(revoked_at=timezone.now())
        self.customer.user.delete()
        return Response(status=204)


class MobileChildrenView(MobileAuthenticatedView):
    @extend_schema(tags=['Дети'], summary='Получить детей клиента', auth=['MobileBearer'], responses={200: None, 401: None})
    def get(self, request):
        return Response({"data": [serialize_child(child) for child in self.customer.children.order_by("id")], "max_children": MAX_CHILDREN})

    @extend_schema(
        tags=['Дети'],
        summary='Добавить ребёнка',
        description='Для одного клиента можно добавить не более двух детей.',
        auth=['MobileBearer'],
        request=ChildRequestSerializer,
        responses={201: None, 400: None, 401: None, 422: None},
    )
    def post(self, request):
        if self.customer.children.count() >= MAX_CHILDREN:
            return error_response(422, "MAX_CHILDREN_REACHED", "Уже добавлено 2 ребёнка")
        name = str(request.data.get("name") or "").strip()
        raw_date_of_birth = str(request.data.get("date_of_birth") or "")
        if not CHILD_NAME_RE.fullmatch(name):
            return error_response(400, "VALIDATION_ERROR", "Имя ребёнка должно содержать от 1 до 50 букв", "name")
        try:
            date_of_birth = date.fromisoformat(raw_date_of_birth)
        except ValueError:
            return error_response(400, "VALIDATION_ERROR", "Дата должна быть в формате YYYY-MM-DD", "date_of_birth")
        today = timezone.localdate()
        if date_of_birth >= today or date_of_birth < date(today.year - 18, today.month, today.day):
            return error_response(422, "INVALID_DATE", "Возраст ребёнка должен быть от 0 до 18 лет", "date_of_birth")
        child = CustomerChild.objects.create(customer=self.customer, name=name, date_of_birth=date_of_birth)
        return Response(serialize_child(child), status=201)


class MobileChildDetailView(MobileAuthenticatedView):
    @extend_schema(tags=['Дети'], summary='Изменить данные ребёнка', auth=['MobileBearer'], request=ChildRequestSerializer, responses={200: None, 400: None, 401: None, 404: None})
    def patch(self, request, child_id):
        child = self.customer.children.filter(id=child_id).first()
        if not child:
            return error_response(404, "NOT_FOUND", "Ребёнок не найден")
        if "name" in request.data:
            name = str(request.data.get("name") or "").strip()
            if not CHILD_NAME_RE.fullmatch(name):
                return error_response(400, "VALIDATION_ERROR", "Имя ребёнка должно содержать от 1 до 50 букв", "name")
            child.name = name
        if "date_of_birth" in request.data:
            try:
                date_of_birth = date.fromisoformat(str(request.data.get("date_of_birth") or ""))
            except ValueError:
                return error_response(400, "VALIDATION_ERROR", "Дата должна быть в формате YYYY-MM-DD", "date_of_birth")
            if date_of_birth >= timezone.localdate():
                return error_response(422, "INVALID_DATE", "Дата рождения должна быть в прошлом", "date_of_birth")
            child.date_of_birth = date_of_birth
        child.save()
        return Response(serialize_child(child))

    @extend_schema(tags=['Дети'], summary='Удалить ребёнка', auth=['MobileBearer'], responses={204: None, 401: None, 404: None})
    def delete(self, request, child_id):
        child = self.customer.children.filter(id=child_id).first()
        if not child:
            return error_response(404, "NOT_FOUND", "Ребёнок не найден")
        child.delete()
        return Response(status=204)