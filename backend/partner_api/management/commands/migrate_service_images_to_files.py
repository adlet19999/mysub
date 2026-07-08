from django.core.management.base import BaseCommand
from django.db import transaction

from partner_api.models import Service
from partner_api.views import save_service_image_from_base64


class Command(BaseCommand):
    help = "Convert legacy Service.image_base64 images to file URLs and clear base64 payloads"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes. Without this flag command runs in dry-run mode.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Optional max number of services to process (0 = no limit).",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        limit = int(options["limit"] or 0)

        queryset = Service.objects.exclude(image_base64="").order_by("id")
        if limit > 0:
            queryset = queryset[:limit]

        total = 0
        migrated = 0
        skipped = 0
        errors = 0

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(self.style.WARNING(f"Running in {mode} mode"))

        for item in queryset.iterator():
            total += 1
            raw = (item.image_base64 or "").strip()
            if not raw:
                skipped += 1
                continue

            if not raw.startswith("data:image/"):
                skipped += 1
                continue

            image_url, image_error = save_service_image_from_base64(
                raw,
                item.tenant_slug,
                item.partner_profile_id or 0,
            )

            if image_error:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Service id={item.id}: conversion failed: {image_error}"
                    )
                )
                continue

            if apply_changes:
                with transaction.atomic():
                    item.image_url = image_url
                    item.image_base64 = ""
                    item.save(update_fields=["image_url", "image_base64"])

            migrated += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Migration summary:"))
        self.stdout.write(f"  total candidates: {total}")
        self.stdout.write(f"  migrated: {migrated}")
        self.stdout.write(f"  skipped (not data:image): {skipped}")
        self.stdout.write(f"  errors: {errors}")

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Dry-run only. Re-run with --apply to persist changes."))
