import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from common_api.models import SubscriptionPlan
from partner_api.views import active_subscription_phones
from .account_views import validate
from .models import CustomerSubscription, MobileDeletionReceipt, MobilePushDevice
from .push import push_configured
from .views import MobileAPIView, MobileAuthenticatedView, error_response


class PushDeviceRequestSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=["android", "ios", "web"])
    token = serializers.CharField(min_length=1, max_length=4096, trim_whitespace=False, write_only=True)

    def validate_token(self, value):
        if not value.isascii() or any(char.isspace() or ord(char) < 33 or ord(char) > 126 for char in value):
            raise serializers.ValidationError("Invalid registration token")
        return value


class PushDeviceResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    platform = serializers.CharField()
    is_active = serializers.BooleanField()
    updated_at = serializers.DateTimeField()


class MobilePushDeviceView(MobileAuthenticatedView):
    @extend_schema(tags=["5. Аккаунт"], request=PushDeviceRequestSerializer,
                   summary="Register or rotate a push token for this installation and session",
                   responses={200: PushDeviceResponseSerializer, 400: None, 409: None, 503: None})
    def put(self, request, device_id):
        serializer = PushDeviceRequestSerializer(data=request.data)
        error = validate(serializer)
        if error is not None:
            return error
        if not push_configured():
            return error_response(503, "PUSH_NOT_CONFIGURED", "Push delivery is not configured")
        data = serializer.validated_data
        token_hash = hashlib.sha256(data["token"].encode()).hexdigest()
        matches = list(MobilePushDevice.objects.select_for_update().filter(
            Q(id=device_id) | Q(token_hash=token_hash),
        ))
        if len(matches) > 1:
            return error_response(409, "DEVICE_TOKEN_CONFLICT", "Unregister the previous installation first")
        device = matches[0] if matches else MobilePushDevice(id=device_id)
        if device.pk != device_id:
            return error_response(409, "DEVICE_TOKEN_CONFLICT", "Token belongs to another installation ID")
        if device.customer_id and device.customer_id != self.customer.id and device.token_hash != token_hash:
            return error_response(409, "DEVICE_IN_USE", "Installation belongs to another account")
        device.customer = self.customer
        device.session = self.mobile_session
        device.platform = data["platform"]
        device.token = data["token"]
        device.token_hash = token_hash
        device.is_active = True
        try:
            with transaction.atomic():
                device.save()
        except IntegrityError:
            return error_response(409, "DEVICE_TOKEN_CONFLICT", "Registration changed; retry with the current token")
        return Response(PushDeviceResponseSerializer(device).data)

    @extend_schema(tags=["5. Аккаунт"], responses={204: None},
                   summary="Unregister this session's push installation")
    def delete(self, request, device_id):
        MobilePushDevice.objects.filter(id=device_id, customer=self.customer, session=self.mobile_session).update(is_active=False)
        return Response(status=204)


class SubscriptionPlanSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    monthly_price = serializers.DecimalField(max_digits=20, decimal_places=2)
    duration_months = serializers.IntegerField()
    description = serializers.CharField()


class SubscriptionPlanListSerializer(serializers.Serializer):
    data = SubscriptionPlanSerializer(many=True)
    currency = serializers.CharField()
    is_complete = serializers.BooleanField()
    checkout_available = serializers.BooleanField()
    price_is_checkout_quote = serializers.BooleanField()


class MobileSubscriptionPlansView(MobileAPIView):
    @extend_schema(tags=["5. Аккаунт"], responses={200: SubscriptionPlanListSerializer},
                   summary="Published admin-managed plans; not a checkout quote")
    def get(self, request):
        return Response({"data": SubscriptionPlanSerializer(
            SubscriptionPlan.objects.filter(is_archived=False).order_by("monthly_price", "id"), many=True,
        ).data, "currency": "KZT", "is_complete": True, "checkout_available": False,
            "price_is_checkout_quote": False})


class SubscriptionStateSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    plan_name = serializers.CharField(allow_null=True)
    status = serializers.ChoiceField(choices=["absent", "active", "paused", "expired"])
    is_active = serializers.BooleanField()
    expires_on = serializers.DateField(allow_null=True)
    expiry_date_inclusive = serializers.BooleanField()
    time_zone = serializers.CharField()
    source = serializers.CharField()
    quote_required = serializers.BooleanField()
    checkout_available = serializers.BooleanField()


class MobileSubscriptionView(MobileAuthenticatedView):
    @extend_schema(tags=["5. Аккаунт"], responses={200: SubscriptionStateSerializer},
                   summary="Read the existing account subscription without activating benefits")
    def get(self, request):
        item = CustomerSubscription.objects.filter(customer=self.customer).first()
        active = self.customer.phone in active_subscription_phones([self.customer.phone])
        status = "absent"
        if item:
            status = "expired" if item.expires_at and item.expires_at < timezone.localdate() else item.status
        return Response({"id": item.id if item else None, "plan_name": item.plan_name if item else None,
                         "status": status, "is_active": active, "expires_on": item.expires_at if item else None,
                         "expiry_date_inclusive": True, "time_zone": timezone.get_current_timezone_name(),
                         "source": "admin_assigned", "quote_required": True, "checkout_available": False})


def deletion_receipt(raw):
    try:
        identity, secret = raw.split(".", 1)
        identity = uuid.UUID(identity)
    except (ValueError, AttributeError):
        return None
    if len(secret) != 43:
        return None
    receipt = MobileDeletionReceipt.objects.filter(id=identity, expires_at__gt=timezone.now()).first()
    if receipt and secrets.compare_digest(receipt.secret_hash, hashlib.sha256(secret.encode()).hexdigest()):
        return receipt
    return None


class DeletionReceiptSerializer(serializers.Serializer):
    receipt = serializers.CharField(max_length=100, write_only=True)


class DeletionRequestResponseSerializer(serializers.Serializer):
    receipt = serializers.CharField()
    expires_at = serializers.DateTimeField()
    state = serializers.CharField()
    deletion_ui_ready = serializers.BooleanField()


class DeletionStatusSerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=["requested", "deleted"])
    completed_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField()


class MobileDeletionRequestView(MobileAuthenticatedView):
    throttle_scope = "mobile_deletion"

    @extend_schema(tags=["3. Профиль клиента"], request=None,
                   summary="Prepare a private receipt; does not delete the account",
                   responses={201: DeletionRequestResponseSerializer})
    def post(self, request):
        secret = secrets.token_urlsafe(32)
        receipt = MobileDeletionReceipt.objects.create(
            customer=self.customer, session=self.mobile_session,
            secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(days=settings.MOBILE_DELETION_RECEIPT_DAYS),
        )
        return Response({"receipt": f"{receipt.id}.{secret}", "expires_at": receipt.expires_at,
                         "state": "requested", "deletion_ui_ready": False}, status=201)


class MobileDeletionStatusView(MobileAPIView):
    throttle_scope = "mobile_deletion"

    @extend_schema(tags=["3. Профиль клиента"], request=DeletionReceiptSerializer,
                   summary="Confirm deletion after a lost response using the private receipt, not a revoked JWT",
                   responses={200: DeletionStatusSerializer, 400: None, 404: None})
    def post(self, request):
        serializer = DeletionReceiptSerializer(data=request.data)
        error = validate(serializer)
        if error is not None:
            return error
        receipt = deletion_receipt(serializer.validated_data["receipt"])
        if receipt is None:
            return error_response(404, "RECEIPT_NOT_FOUND", "Receipt is invalid or expired")
        return Response({"state": "deleted" if receipt.completed_at else "requested",
                         "completed_at": receipt.completed_at, "expires_at": receipt.expires_at})
