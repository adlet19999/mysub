import re
import uuid
from io import BytesIO
from pathlib import Path
from datetime import date, timedelta

import jwt
from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from common_api.views import normalize_ru_phone

from .models import CustomerChild, CustomerProfile, MobileRefreshSession
from .serializers import (
    AuthenticationResponseSerializer,
    AvatarUploadRequestSerializer,
    AvatarUploadResponseSerializer,
    CityListResponseSerializer,
    CustomerResponseSerializer,
    CustomerUpdateRequestSerializer,
    RefreshTokenResponseSerializer,
    RefreshTokenRequestSerializer,
    SendCodeResponseSerializer,
    SendCodeRequestSerializer,
    VerifyCodeRequestSerializer,
)
from .models import City


PHONE_RE = re.compile(r"^\+7\d{10}$")
CHILD_NAME_RE = re.compile(r"^[^\d_]{1,50}$")
MAX_CHILDREN = 2
MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 25_000_000
AVATAR_URL_PREFIX = "/api/v1/mobile/avatar-images/"


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
    return {
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


def delete_stored_avatar(avatar_url):
    if not avatar_url or not avatar_url.startswith(AVATAR_URL_PREFIX):
        return
    file_name = avatar_url.removeprefix(AVATAR_URL_PREFIX)
    if file_name != Path(file_name).name:
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
        self.customer = CustomerProfile.objects.select_related("user", "city").filter(id=payload["sub"]).first()
        if not self.customer:
            self.permission_denied(request, message="UNAUTHORIZED")

    def handle_exception(self, exc):
        if getattr(exc, "detail", None) == "UNAUTHORIZED":
            return error_response(401, "UNAUTHORIZED", "Недействительный access token")
        return super().handle_exception(exc)


class MobileCitiesView(APIView):
    @extend_schema(
        tags=['0. Справочники'],
        summary='Получить список городов',
        description='Используйте `id` выбранного города в поле `city_id` при заполнении профиля. Название города вручную передавать не нужно.',
        responses={200: CityListResponseSerializer},
    )
    def get(self, request):
        cities = City.objects.filter(is_active=True)
        return Response({"data": [{"id": city.id, "name": city.name} for city in cities]})


class MobileAuthSendCodeView(APIView):
    @extend_schema(
        tags=['1. Регистрация и вход'],
        summary='Шаг 1. Запросить одноразовый SMS-код',
        description=(
            'Передайте номер телефона. Сервер отправляет одноразовый код на этот номер. '
            'Код не возвращается в API-ответе, действует ограниченное время и используется '
            'на следующем шаге регистрации или входа.'
        ),
        request=SendCodeRequestSerializer,
        responses={200: SendCodeResponseSerializer, 400: None},
    )
    def post(self, request):
        phone = normalize_ru_phone(str(request.data.get("phone") or ""))
        if not PHONE_RE.fullmatch(phone):
            return error_response(400, "VALIDATION_ERROR", "Неверный формат номера", "phone")
        return Response({"message": "Code sent", "expires_in": 120, "retry_after": 120})


class MobileAuthVerifyCodeView(APIView):
    @extend_schema(
        tags=['1. Регистрация и вход'],
        summary='Шаг 3B. Войти в существующий аккаунт',
        description=(
            'Используйте после шага 1, если клиент уже зарегистрирован. '
            'При успешной проверке кода клиент не создаётся повторно: API возвращает профиль '
            'и новую пару JWT-токенов. В режиме разработки принимается код `11111`.'
        ),
        request=VerifyCodeRequestSerializer,
        responses={200: AuthenticationResponseSerializer, 400: None, 401: None, 404: None},
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
        if customer is None:
            return error_response(404, "USER_NOT_FOUND", "Клиент с этим номером не зарегистрирован", "phone")
        return Response({"user": serialize_customer(customer, request), "tokens": issue_tokens(customer), "is_new_user": False})


class MobileAuthRegisterView(APIView):
    @extend_schema(
        tags=['1. Регистрация и вход'],
        summary='Шаг 3A. Создать нового клиента',
        description=(
            'Используйте после шага 1 только для нового номера. API сверяет одноразовый SMS-код, '
            'создаёт профиль клиента и возвращает JWT-токены. После ответа с `is_new_user: true` '
            'вызовите `PATCH /users/me/`, чтобы заполнить имя и город. '
            'В режиме разработки принимается код `11111`.'
        ),
        request=VerifyCodeRequestSerializer,
        responses={201: AuthenticationResponseSerializer, 400: None, 401: None, 409: None},
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
        if CustomerProfile.objects.filter(phone=phone).exists():
            return error_response(409, "USER_ALREADY_EXISTS", "Клиент с этим номером уже зарегистрирован", "phone")

        with transaction.atomic():
            user = User.objects.create_user(username=f"mobile:{phone}", password=None)
            customer = CustomerProfile.objects.create(
                user=user,
                phone=phone,
                language=get_request_language(request),
            )
        return Response({"user": serialize_customer(customer, request), "tokens": issue_tokens(customer), "is_new_user": True}, status=201)


class MobileAuthRefreshView(APIView):
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
        if "avatar_url" in request.data:
            avatar_url = str(request.data.get("avatar_url") or "").strip()
            if avatar_url and not avatar_url.startswith(("http://", "https://")):
                return error_response(400, "VALIDATION_ERROR", "Некорректный URL фотографии", "avatar_url")
            customer.avatar_url = avatar_url
        if "city_id" in request.data:
            city = City.objects.filter(id=request.data.get("city_id"), is_active=True).first()
            if not city:
                return error_response(400, "VALIDATION_ERROR", "Город не найден", "city_id")
            customer.city = city
        if "language" in request.data:
            language = str(request.data.get("language") or "").strip().lower()
            if language not in {"ru", "kk", "en"}:
                return error_response(400, "VALIDATION_ERROR", "Поддерживаются языки ru, kk, en", "language")
            customer.language = language
        if "agreement_accepted" in request.data:
            customer.agreement_accepted = bool(request.data.get("agreement_accepted"))
        if "agreement_version" in request.data:
            customer.agreement_version = str(request.data.get("agreement_version") or "").strip()[:40]

        children_data = request.data.get("children")
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
                if not CHILD_NAME_RE.fullmatch(name):
                    return error_response(400, "VALIDATION_ERROR", "Имя ребёнка должно содержать от 1 до 50 букв", "children")
                try:
                    date_of_birth = date.fromisoformat(str(child_data.get("date_of_birth") or ""))
                except ValueError:
                    return error_response(400, "VALIDATION_ERROR", "Дата ребёнка должна быть в формате YYYY-MM-DD", "children")
                if date_of_birth >= today or date_of_birth < date(today.year - 18, today.month, today.day):
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
        return Response(serialize_customer(customer, request))

    @extend_schema(tags=['3. Профиль клиента'], summary='Удалить аккаунт текущего клиента', auth=[{'MobileBearer': []}], responses={204: None, 401: None})
    def delete(self, request):
        MobileRefreshSession.objects.filter(customer=self.customer).update(revoked_at=timezone.now())
        self.customer.user.delete()
        return Response(status=204)


class MobileCurrentUserAvatarView(MobileAuthenticatedView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=['3. Профиль клиента'],
        summary='Загрузить или заменить фотографию клиента',
        description='Передайте файл в поле `file` как `multipart/form-data`. Допускаются изображения до 5 MB; сервер уменьшает их и сохраняет в WebP.',
        auth=[{'MobileBearer': []}],
        request=AvatarUploadRequestSerializer,
        responses={200: AvatarUploadResponseSerializer, 400: None, 401: None},
    )
    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return error_response(400, "VALIDATION_ERROR", "Передайте изображение в поле file", "file")

        avatar_url, error = save_customer_avatar(uploaded_file, self.customer.id)
        if error:
            return error_response(400, "INVALID_IMAGE", error, "file")

        previous_avatar_url = self.customer.avatar_url
        self.customer.avatar_url = avatar_url
        self.customer.save(update_fields=["avatar_url", "updated_at"])
        delete_stored_avatar(previous_avatar_url)
        return Response({"avatar_url": request.build_absolute_uri(avatar_url)})