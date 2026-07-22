from django.core.management.base import BaseCommand
from django.db import transaction

from partner_api.models import Manager, Specialist
from partner_api.views import compress_image_base64, save_profile_image_from_base64


class Command(BaseCommand):
    help = "Move manager and specialist base64 photos to WebP files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes. Without this flag command runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        total = 0
        migrated = 0
        skipped = 0
        errors = 0

        for model, image_type in ((Manager, "manager"), (Specialist, "specialist")):
            queryset = model.objects.exclude(photo_base64="").order_by("id")
            for item in queryset.iterator():
                total += 1
                if item.photo_url:
                    skipped += 1
                    continue

                if apply_changes:
                    photo_url, error = save_profile_image_from_base64(
                        item.photo_base64,
                        item.tenant_slug,
                        item.partner_profile_id or 0,
                        image_type,
                    )
                else:
                    _, error = compress_image_base64(item.photo_base64)
                    photo_url = ""
                if error:
                    errors += 1
                    self.stdout.write(self.style.ERROR(f"{model.__name__} id={item.id}: {error}"))
                    continue

                if apply_changes:
                    with transaction.atomic():
                        item.photo_url = photo_url
                        item.photo_base64 = ""
                        item.save(update_fields=["photo_url", "photo_base64"])
                migrated += 1

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(self.style.SUCCESS(f"Migration summary ({mode}):"))
        self.stdout.write(f"  total photos: {total}")
        self.stdout.write(f"  migrated: {migrated}")
        self.stdout.write(f"  skipped: {skipped}")
        self.stdout.write(f"  errors: {errors}")