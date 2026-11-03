from django.core.management.base import BaseCommand
from django.utils import timezone

from mobile_api.models import MobileDeletionReceipt


class Command(BaseCommand):
    help = "Remove expired deletion reconciliation receipts; does not delete customer accounts."

    def handle(self, *args, **options):
        count, _ = MobileDeletionReceipt.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f"Deleted {count} expired receipt(s).")
