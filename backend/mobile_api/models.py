from django.conf import settings
from django.db import models
import uuid
from django.core.exceptions import ValidationError
from django.utils import timezone


class City(models.Model):
    name = models.CharField(max_length=120, unique=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("display_order", "name")

    def __str__(self):
        return self.name


class CustomerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    phone = models.CharField(max_length=12, unique=True)
    city = models.ForeignKey(
        City,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="customer_profiles",
    )
    language = models.CharField(max_length=2, default="ru")
    avatar_url = models.URLField(blank=True, default="")
    agreement_accepted = models.BooleanField(default=False)
    agreement_version = models.CharField(max_length=40, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CustomerSubscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активна"
        PAUSED = "paused", "Приостановлена"

    customer = models.OneToOneField(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan_name = models.CharField(max_length=120, default="Базовая")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CustomerChild(models.Model):
    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="children",
    )
    name = models.CharField(max_length=50)
    date_of_birth = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)


class MobileRefreshSession(models.Model):
    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name="refresh_sessions",
    )
    token_id = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PhoneChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=12)
    purpose = models.CharField(max_length=20, default="signin")
    customer = models.ForeignKey(CustomerProfile, null=True, on_delete=models.CASCADE)
    session_id = models.CharField(max_length=64, blank=True)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    delivery_mode = models.CharField(max_length=12, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["phone", "purpose"], name="uniq_mobile_phone_challenge"),
        ]


class BookingResource(models.Model):
    partner = models.ForeignKey("common_api.PartnerProfile", on_delete=models.CASCADE, related_name="mobile_resources")
    services = models.ManyToManyField("partner_api.Service", related_name="mobile_resources")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=[("hall", "Hall"), ("unit", "Unit")])
    capacity = models.PositiveSmallIntegerField(default=1)
    working_schedule = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(capacity__gte=1), name="mobile_resource_positive_capacity"),
        ]

    def clean(self):
        from partner_api.views import normalize_working_schedule
        _, error = normalize_working_schedule(self.working_schedule)
        if error:
            raise ValidationError({"working_schedule": error})


class MobileBookingRecord(models.Model):
    booking = models.OneToOneField("partner_api.Booking", on_delete=models.CASCADE, related_name="mobile_record")
    customer = models.ForeignKey(CustomerProfile, null=True, on_delete=models.SET_NULL, related_name="booking_records")
    owner_claimed = models.BooleanField(default=False)
    comment = models.CharField(max_length=2000, blank=True)
    attendee = models.JSONField(default=dict)
    vehicle = models.JSONField(default=dict)
    resource = models.ForeignKey(BookingResource, null=True, on_delete=models.PROTECT, related_name="booking_records")
    resource_snapshot = models.JSONField(default=dict)
    batch_id = models.UUIDField(null=True)
    notified_state = models.CharField(max_length=64, blank=True)


class MobileBookingRequest(models.Model):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE)
    request_id = models.UUIDField()
    operation = models.CharField(max_length=24)
    payload = models.JSONField()
    booking_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["customer", "request_id", "operation"], name="uniq_mobile_booking_request"),
        ]


class BookingReview(models.Model):
    booking = models.OneToOneField("partner_api.Booking", on_delete=models.CASCADE, related_name="mobile_review")
    customer = models.ForeignKey(CustomerProfile, null=True, on_delete=models.SET_NULL)
    rating = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=2000, blank=True)
    language = models.CharField(max_length=2, default="ru")
    state = models.CharField(max_length=12, default="pending", choices=[
        ("pending", "Pending"), ("published", "Published"), ("hidden", "Hidden"),
    ])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(rating__gte=1, rating__lte=5), name="mobile_review_rating_bounds"),
        ]


class Favorite(models.Model):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="favorites")
    partner = models.ForeignKey("common_api.PartnerProfile", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["customer", "partner"], name="uniq_mobile_favorite"),
        ]


class MobileNotification(models.Model):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=40)
    booking = models.ForeignKey("partner_api.Booking", null=True, on_delete=models.SET_NULL)
    parameters = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True)


class NotificationPreferences(models.Model):
    customer = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE)
    delivery_enabled = models.BooleanField(default=True)
    bookings_enabled = models.BooleanField(default=True)
    offers_enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class MobileContent(models.Model):
    key = models.CharField(max_length=80)
    kind = models.CharField(max_length=12, choices=[("faq", "FAQ"), ("legal", "Legal"), ("support", "Support")])
    language = models.CharField(max_length=2, choices=[("ru", "Russian"), ("kk", "Kazakh"), ("en", "English")])
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.URLField(blank=True)
    version = models.CharField(max_length=40)
    effective_at = models.DateTimeField()
    display_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    def clean(self):
        if self.is_published and not self.body.strip() and not self.url:
            raise ValidationError("Published content requires an approved body or URL")
        if self.is_published and self.kind == "legal" and self.url and not self.url.startswith("https://"):
            raise ValidationError({"url": "Published legal destinations must use HTTPS"})

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key", "language"], name="uniq_mobile_content_locale"),
        ]


class MobilePushDevice(models.Model):
    id = models.UUIDField(primary_key=True)
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="push_devices")
    session = models.ForeignKey(MobileRefreshSession, on_delete=models.CASCADE, related_name="push_devices")
    platform = models.CharField(max_length=8, choices=[("android", "Android"), ("ios", "iOS"), ("web", "Web")])
    token = models.CharField(max_length=4096)
    token_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)


class MobilePushDelivery(models.Model):
    notification = models.ForeignKey(MobileNotification, on_delete=models.CASCADE)
    device = models.ForeignKey(MobilePushDevice, on_delete=models.CASCADE)
    state = models.CharField(max_length=12, default="pending", choices=[
        ("pending", "Pending"), ("delivered", "Gateway accepted"), ("skipped", "Skipped"), ("failed", "Failed"),
    ])
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["notification", "device"], name="uniq_mobile_push_delivery"),
        ]
        indexes = [models.Index(fields=["state", "available_at"], name="mobile_push_pending_idx")]


class MobileDeletionReceipt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    secret_hash = models.CharField(max_length=64)
    customer = models.ForeignKey(CustomerProfile, null=True, on_delete=models.SET_NULL)
    session = models.ForeignKey(MobileRefreshSession, null=True, on_delete=models.SET_NULL)
    requested_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(null=True)