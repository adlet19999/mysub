from django.db.models.signals import post_save
from django.dispatch import receiver

from partner_api.models import Booking
from .booking_contract import sync_booking_record
from .models import MobileNotification
from .push import enqueue_notification


@receiver(post_save, sender=Booking)
def sync_mobile_booking(sender, instance, raw=False, **kwargs):
    if not raw and instance.tenant_slug == "public" and instance.partner_profile_id:
        sync_booking_record(instance)


@receiver(post_save, sender=MobileNotification)
def enqueue_mobile_push(sender, instance, created=False, raw=False, **kwargs):
    if created and not raw:
        enqueue_notification(instance)
