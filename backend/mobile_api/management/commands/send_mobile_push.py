import time

from django.core.management.base import BaseCommand, CommandError

from mobile_api.push import deliver_pending, push_configured


class Command(BaseCommand):
    help = "Deliver a bounded batch of queued mobile pushes using the configured gateway adapter."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--watch", action="store_true")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("--limit must be between 1 and 1000")
        if not push_configured():
            raise CommandError("MOBILE_PUSH_SENDER is not configured")
        while True:
            counts = deliver_pending(options["limit"])
            if not options["watch"] or any(counts.values()):
                self.stdout.write(", ".join(f"{key}={value}" for key, value in counts.items()))
            if not options["watch"]:
                return
            time.sleep(10)
