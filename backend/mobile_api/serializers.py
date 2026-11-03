from rest_framework import serializers
from decimal import Decimal
import re


class OffsetDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value):
        if not isinstance(value, str) or not re.search(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$", value):
            raise serializers.ValidationError("Укажите ISO 8601 с часовым поясом")
        return super().to_internal_value(value)


class SendCodeRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(help_text='Номер в формате +7XXXXXXXXXX')


class VerifyCodeRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(help_text='Номер в формате +7XXXXXXXXXX')
    code = serializers.CharField(help_text='Одноразовый код из SMS', min_length=4, max_length=8)
    language = serializers.ChoiceField(choices=["ru", "kk", "en"], required=False)


class RefreshTokenRequestSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(help_text='Refresh token, полученный при регистрации или входе')


class LogoutRequestSerializer(serializers.Serializer):
    all_devices = serializers.BooleanField(required=False, default=False)


class SendCodeResponseSerializer(serializers.Serializer):
    message = serializers.CharField(help_text='Статус отправки SMS')
    expires_in = serializers.IntegerField(help_text='Срок действия кода в секундах')
    retry_after = serializers.IntegerField(help_text='Через сколько секунд можно запросить код повторно')
    challenge_id = serializers.UUIDField()
    delivery_mode = serializers.ChoiceField(choices=["test", "provider"])


class TokenPairSerializer(serializers.Serializer):
    access_token = serializers.CharField(help_text='JWT для запросов к защищённым endpoint, действует 1 час')
    refresh_token = serializers.CharField(help_text='JWT для обновления сессии, хранится в защищённом хранилище')
    token_type = serializers.CharField(help_text='Тип токена для заголовка Authorization')
    expires_in = serializers.IntegerField(help_text='Срок действия access token в секундах')


class ChildSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, help_text='Передавайте только для уже созданного ребёнка')
    name = serializers.CharField(help_text='Имя ребёнка от 1 до 50 букв')
    date_of_birth = serializers.DateField(help_text='Дата в формате YYYY-MM-DD')
    age = serializers.IntegerField(required=False, read_only=True)


class CityResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField(help_text='Идентификатор города для передачи в city_id')
    name = serializers.CharField(help_text='Название города для отображения пользователю')


class CityListResponseSerializer(serializers.Serializer):
    data = CityResponseSerializer(many=True)


class CustomerResponseSerializer(serializers.Serializer):
    id = serializers.CharField()
    phone = serializers.CharField()
    name = serializers.CharField(allow_null=True)
    email = serializers.EmailField(allow_null=True)
    avatar_url = serializers.URLField(allow_null=True)
    city_id = serializers.IntegerField(allow_null=True, help_text='ID выбранного города из GET /cities/')
    city_name = serializers.CharField(allow_null=True)
    language = serializers.ChoiceField(choices=['ru', 'kk', 'en'])
    is_profile_complete = serializers.BooleanField(help_text='true, если заполнены имя и город')
    agreement_accepted = serializers.BooleanField()
    agreement_version = serializers.CharField(allow_null=True)
    children = ChildSerializer(many=True)
    max_children = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    revision = serializers.CharField()


class AuthenticationResponseSerializer(serializers.Serializer):
    user = CustomerResponseSerializer()
    tokens = TokenPairSerializer()
    is_new_user = serializers.BooleanField(help_text='true только после успешной регистрации нового клиента')


class RefreshTokenResponseSerializer(serializers.Serializer):
    tokens = TokenPairSerializer()


class CustomerUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, help_text='Имя от 2 до 100 символов')
    email = serializers.EmailField(required=False, allow_blank=True)
    avatar_url = serializers.URLField(required=False, allow_blank=True, help_text='URL фотографии пользователя')
    city_id = serializers.IntegerField(required=False, min_value=1, help_text='ID города из GET /cities/')
    language = serializers.ChoiceField(choices=['ru', 'kk', 'en'], required=False)
    agreement_accepted = serializers.BooleanField(required=False)
    agreement_version = serializers.CharField(required=False, allow_blank=True, max_length=40)
    children = ChildSerializer(required=False, many=True, help_text='Полный актуальный список детей, не более двух')
    revision = serializers.CharField(required=False, min_length=64, max_length=64)


class AvatarUploadRequestSerializer(serializers.Serializer):
    file = serializers.ImageField(help_text='Файл изображения до 5 MB')


class AvatarUploadResponseSerializer(serializers.Serializer):
    avatar_url = serializers.URLField(help_text='Абсолютная ссылка на сохранённую фотографию')


class CatalogPartnerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    category = serializers.CharField()
    city = serializers.CharField()
    address = serializers.CharField()
    description = serializers.CharField()
    photo_urls = serializers.ListField(child=serializers.URLField())
    phone = serializers.CharField(allow_null=True)
    website = serializers.URLField(allow_null=True)
    instagram = serializers.CharField(allow_null=True)
    working_hours = serializers.CharField(allow_null=True)
    time_zone = serializers.CharField()
    category_id = serializers.IntegerField(allow_null=True)
    category_code = serializers.CharField(allow_null=True)
    verification_status = serializers.CharField()
    rating = serializers.FloatField(allow_null=True)
    rating_count = serializers.IntegerField()


class CatalogPartnerListResponseSerializer(serializers.Serializer):
    data = CatalogPartnerSerializer(many=True)


class CatalogServiceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    partner_id = serializers.IntegerField()
    partner_name = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()
    category_id = serializers.IntegerField(allow_null=True)
    service_category_id = serializers.IntegerField()
    category_code = serializers.CharField(allow_null=True)
    booking_category_code = serializers.CharField(allow_null=True)
    kind = serializers.CharField(allow_null=True)
    description = serializers.CharField()
    duration_minutes = serializers.IntegerField()
    slot_interval_minutes = serializers.IntegerField()
    booking_mode = serializers.ChoiceField(choices=["table", "specialist", "resource"])
    price = serializers.CharField(allow_null=True)
    service_type = serializers.CharField()
    is_pass = serializers.BooleanField()
    visit_count = serializers.IntegerField()
    pass_price_mode = serializers.ChoiceField(choices=["per_visit", "total"])
    image_url = serializers.URLField(allow_blank=True)
    resource_ids = serializers.ListField(child=serializers.IntegerField())
    audience = serializers.CharField(allow_null=True)
    min_age = serializers.IntegerField(allow_null=True)
    max_age = serializers.IntegerField(allow_null=True)
    requires_occurrence = serializers.BooleanField()
    discount_percent = serializers.IntegerField()
    is_promo = serializers.BooleanField()
    currency = serializers.CharField()


class CatalogServiceListResponseSerializer(serializers.Serializer):
    data = CatalogServiceSerializer(many=True)


class CatalogSpecialistSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    description = serializers.CharField()
    photo_url = serializers.URLField(allow_blank=True)
    service_ids = serializers.ListField(child=serializers.IntegerField())
    service_names = serializers.ListField(child=serializers.CharField())


class CatalogSpecialistListResponseSerializer(serializers.Serializer):
    data = CatalogSpecialistSerializer(many=True)


class AllocationSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    specialist_ids = serializers.ListField(child=serializers.IntegerField())
    resource_ids = serializers.ListField(child=serializers.IntegerField())


class AvailabilityResponseSerializer(serializers.Serializer):
    date = serializers.DateField()
    time_zone = serializers.CharField(help_text="Часовой пояс возвращаемых слотов")
    duration_minutes = serializers.IntegerField()
    slot_interval_minutes = serializers.IntegerField()
    slots = serializers.ListField(child=serializers.TimeField(format="%H:%M"))
    allocations = AllocationSerializer(many=True, required=False)
    is_complete = serializers.BooleanField(required=False)


class ServiceAvailabilitySerializer(AvailabilityResponseSerializer):
    allocations = AllocationSerializer(many=True)
    is_complete = serializers.BooleanField()


class AttendeeRequestSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["self", "child"], default="self")
    child_id = serializers.IntegerField(min_value=1, required=False)


class VehicleRequestSerializer(serializers.Serializer):
    model = serializers.CharField(max_length=120)
    registration_plate = serializers.CharField(max_length=32)


class BookingEntryCreateSerializer(serializers.Serializer):
    service_id = serializers.IntegerField(min_value=1)
    specialist_id = serializers.IntegerField(min_value=1)
    starts_at = OffsetDateTimeField()
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class MobileBookingCreateRequestSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField(min_value=1, help_text="ID партнёра из каталога")
    specialist_id = serializers.IntegerField(min_value=1, required=False, help_text="Обязателен для обычной услуги; для ресторана не передаётся")
    party_size = serializers.IntegerField(min_value=1, max_value=1000, required=False, help_text="Количество гостей; обязательно для ресторана, столик выбирает сервер")
    service_id = serializers.IntegerField(min_value=1, required=False, help_text="ID выбранной услуги")
    starts_at = OffsetDateTimeField(required=False, help_text="Начало записи в ISO 8601 с offset +05:00 для Алматы; время должно совпадать со свободным слотом")
    visits = serializers.ListField(child=OffsetDateTimeField(), required=False, max_length=365, help_text="Для абонемента: все даты посещений, starts_at совпадает с первой датой")
    request_id = serializers.UUIDField(required=False, help_text="Ключ повторного запроса в рамках аккаунта; обязателен для абонемента и entries, рекомендован для любой записи")
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    attendee = AttendeeRequestSerializer(required=False)
    vehicle = VehicleRequestSerializer(required=False)
    resource_id = serializers.IntegerField(required=False, min_value=1)
    group_session_id = serializers.IntegerField(required=False, min_value=1)
    expected_final_price = serializers.DecimalField(required=False, max_digits=16, decimal_places=2, min_value=Decimal("0.00"))
    entries = BookingEntryCreateSerializer(many=True, required=False, min_length=1, max_length=10)


class PassVisitSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    visit_number = serializers.IntegerField()
    starts_at = serializers.DateTimeField()
    status = serializers.CharField()
    base_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    final_price = serializers.DecimalField(max_digits=12, decimal_places=2)


class BookingPassSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    group_id = serializers.IntegerField(allow_null=True)
    visit_number = serializers.IntegerField()
    visit_count = serializers.IntegerField()
    price_mode = serializers.ChoiceField(choices=["total", "per_visit"])
    total_price = serializers.DecimalField(max_digits=16, decimal_places=2)
    completed_visits = serializers.IntegerField()
    owned_visit_count = serializers.IntegerField()
    is_complete = serializers.BooleanField()
    visits = PassVisitSerializer(many=True)


class BookingReviewSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    booking_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(allow_blank=True, max_length=2000)
    language = serializers.ChoiceField(choices=["ru", "kk", "en"])
    state = serializers.ChoiceField(choices=["pending", "published", "hidden"])
    created_at = serializers.DateTimeField()


class ReviewRequestSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class RescheduleRequestSerializer(serializers.Serializer):
    starts_at = OffsetDateTimeField()
    specialist_id = serializers.IntegerField(required=False, min_value=1)
    resource_id = serializers.IntegerField(required=False, min_value=1)
    revision = serializers.CharField(min_length=64, max_length=64)
    request_id = serializers.UUIDField()
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    expected_final_price = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, min_value=Decimal("0.00"))


class MobileBookingEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    partner_id = serializers.IntegerField()
    partner_name = serializers.CharField()
    service_name = serializers.CharField()
    specialist_name = serializers.CharField()
    service_id = serializers.IntegerField(allow_null=True)
    service_ids = serializers.ListField(child=serializers.IntegerField())
    specialist_id = serializers.IntegerField(allow_null=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(allow_null=True)
    duration_minutes = serializers.IntegerField(allow_null=True)
    currency = serializers.CharField()
    status = serializers.CharField()
    status_group = serializers.CharField()
    revision = serializers.CharField()
    comment = serializers.CharField(allow_blank=True)
    attendee = serializers.JSONField()
    vehicle = serializers.JSONField()
    resource = serializers.JSONField(allow_null=True)
    base_price = serializers.CharField()
    discount_amount = serializers.CharField()
    final_price = serializers.CharField()
    is_cancellable = serializers.BooleanField()
    cancellation_reason = serializers.CharField(allow_null=True)
    is_reschedulable = serializers.BooleanField()
    is_reviewable = serializers.BooleanField()
    review = BookingReviewSerializer(allow_null=True)
    created_at = serializers.DateTimeField()
    booking_pass = BookingPassSerializer(allow_null=True)
    restaurant = serializers.JSONField(allow_null=True)


class BookingGroupSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    entries = MobileBookingEntrySerializer(many=True)
    is_complete = serializers.BooleanField()


class MobileBookingSerializer(MobileBookingEntrySerializer):
    booking_group = BookingGroupSerializer(allow_null=True)


class MobileBookingListResponseSerializer(serializers.Serializer):
    data = MobileBookingSerializer(many=True)
    total = serializers.IntegerField()
    is_complete = serializers.BooleanField()


class QuotedVisitSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    base_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    final_price = serializers.DecimalField(max_digits=12, decimal_places=2)


class BookingQuoteSerializer(serializers.Serializer):
    partner_id = serializers.IntegerField()
    service_id = serializers.IntegerField()
    specialist_id = serializers.IntegerField(allow_null=True)
    currency = serializers.CharField()
    is_reserved = serializers.BooleanField()
    visits = QuotedVisitSerializer(many=True)
    base_price = serializers.DecimalField(max_digits=16, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    final_price = serializers.DecimalField(max_digits=16, decimal_places=2)
    resource_id = serializers.IntegerField(allow_null=True)
    table_id = serializers.IntegerField(allow_null=True)