import logging
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import MobilePushDelivery, MobilePushDevice, NotificationPreferences


logger = logging.getLogger(__name__)


class PushDeliveryError(Exception):
    """A temporary gateway failure; delivery can be retried."""


class PushTokenInvalid(PushDeliveryError):
    """The gateway rejected a permanently invalid registration token."""


def push_configured():
    return bool(settings.MOBILE_PUSH_SENDER)


def push_allowed(customer_id, notification_type):
    preferences = NotificationPreferences.objects.filter(customer_id=customer_id).first()
    bookings = notification_type.startswith("booking.")
    if preferences is None:
        return bookings
    return preferences.delivery_enabled and (
        preferences.bookings_enabled if bookings else preferences.offers_enabled
    )


def enqueue_notification(notification):
    if not push_configured() or not push_allowed(notification.customer_id, notification.type):
        return
    now = timezone.now()
    devices = MobilePushDevice.objects.filter(
        customer_id=notification.customer_id, is_active=True,
        session__revoked_at__isnull=True, session__expires_at__gt=now,
    )
    MobilePushDelivery.objects.bulk_create([
        MobilePushDelivery(notification=notification, device=device) for device in devices
    ])


def deliver_pending(limit):
    sender = import_string(settings.MOBILE_PUSH_SENDER)
    counts = {"delivered": 0, "skipped": 0, "failed": 0, "retry": 0}
    for _ in range(limit):
        with transaction.atomic():
            query = MobilePushDelivery.objects.filter(state="pending", available_at__lte=timezone.now())
            if connection.features.has_select_for_update_skip_locked:
                query = query.select_for_update(skip_locked=True)
            else:
                query = query.select_for_update()
            delivery = query.order_by("available_at", "id").first()
            if delivery is None:
                break
            device = MobilePushDevice.objects.select_related("session", "customer__user").get(pk=delivery.device_id)
            notification = delivery.notification
            if (not device.is_active or not device.customer.user.is_active
                    or device.customer_id != notification.customer_id
                    or device.session.customer_id != device.customer_id
                    or device.session.revoked_at or device.session.expires_at <= timezone.now()
                    or not push_allowed(device.customer_id, notification.type)):
                delivery.state = "skipped"
                delivery.error_code = "DELIVERY_DISABLED"
                counts["skipped"] += 1
            else:
                delivery.attempts += 1
                try:
                    accepted = sender(token=device.token, platform=device.platform,
                                      data={"type": "inbox.updated"}, delivery_id=str(delivery.id))
                    if accepted is not True:
                        raise PushDeliveryError("Gateway acceptance not acknowledged")
                except PushTokenInvalid:
                    MobilePushDevice.objects.filter(pk=device.pk, token_hash=device.token_hash).update(is_active=False)
                    delivery.state = "failed"
                    delivery.error_code = "INVALID_TOKEN"
                    counts["failed"] += 1
                    logger.warning("Push gateway rejected registration for delivery %s", delivery.id)
                except PushDeliveryError:
                    delivery.error_code = "GATEWAY_UNAVAILABLE"
                    if delivery.attempts >= 5:
                        delivery.state = "failed"
                        counts["failed"] += 1
                    else:
                        delivery.available_at = timezone.now() + timedelta(minutes=2 ** delivery.attempts)
                        counts["retry"] += 1
                    logger.warning("Push gateway did not accept delivery %s (attempt %s)", delivery.id, delivery.attempts)
                else:
                    delivery.state = "delivered"
                    delivery.sent_at = timezone.now()
                    delivery.error_code = ""
                    counts["delivered"] += 1
            delivery.save()
    return counts
