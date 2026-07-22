from django.core.management.base import BaseCommand
from django.db import transaction

from partner_api.models import Specialist
from partner_api.views import compress_image_base64


class Command(BaseCommand):
    help = "Compress existing specialist base64 photos to WebP"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes. Without this flag command runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        queryset = Specialist.objects.exclude(photo_base64="").order_by("id")
        total = 0
        compressed = 0
        errors = 0

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(self.style.WARNING(f"Running in {mode} mode"))

        for specialist in queryset.iterator():
            total += 1
            original_photo = specialist.photo_base64
            compressed_photo, error = compress_image_base64(original_photo)
            if error:
                errors += 1
                self.stdout.write(self.style.ERROR(f"Specialist id={specialist.id}: {error}"))
                continue

            if compressed_photo == original_photo:
                continue

            if apply_changes:
                with transaction.atomic():
                    specialist.photo_base64 = compressed_photo
                    specialist.save(update_fields=["photo_base64"])
            compressed += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Compression summary:"))
        self.stdout.write(f"  total photos: {total}")
        self.stdout.write(f"  compressed: {compressed}")
        self.stdout.write(f"  errors: {errors}")

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Dry-run only. Re-run with --apply to persist changes."))
