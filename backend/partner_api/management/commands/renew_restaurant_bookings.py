import logging
import time

from django.core.management.base import BaseCommand
from django.db import DatabaseError, close_old_connections

from partner_api.restaurant import renew_restaurant_bookings


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Extend confirmed restaurant visits by two hours until paid completion."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")

    def handle(self, *args, **options):
        while True:
            try:
                close_old_connections()
                count = renew_restaurant_bookings()
                if count:
                    self.stdout.write(f"Extended restaurant visits: {count}")
            except DatabaseError:
                if not options["watch"]:
                    raise
                logger.exception("Restaurant renewal failed; retrying in 30 seconds")
            if not options["watch"]:
                return
            time.sleep(30)
