from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
import uuid

from django.contrib.auth.models import User
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from partner_api.models import Booking
from partner_api.test_lifecycle import LifecycleFixture
from .models import CustomerProfile, MobileNotification, MobilePushDelivery, MobilePushDevice, MobileRefreshSession
from .push import deliver_pending
from .views import issue_tokens


@skipUnless(connection.vendor == "postgresql", "Concurrency requires PostgreSQL row locks")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MobileConcurrencyTests(LifecycleFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.book().status_code, 201)
        self.tokens = []
        for index in range(2):
            customer = CustomerProfile.objects.create(
                user=User.objects.create_user(username=f"concurrent-mobile-{index}", first_name="Участник"),
                phone=f"+7700000200{index}",
            )
            self.tokens.append(issue_tokens(customer)["access_token"])

    def reserve(self, token, request_id, barrier):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            response = APIClient().post(
                "/api/v1/mobile/bookings/",
                {"partner_id": self.partner.id, "service_id": self.service.id,
                 "specialist_id": self.specialist.id, "starts_at": self.starts_at.isoformat(),
                 "request_id": str(request_id)},
                format="json", HTTP_AUTHORIZATION=f"Bearer {token}",
            )
            return response.status_code, response.data.get("id")
        finally:
            close_old_connections()

    def test_competing_accounts_cannot_take_last_group_seat(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.reserve, token, uuid.uuid4(), barrier) for token in self.tokens]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(sorted(status for status, _ in results), [201, 409])
        self.assertEqual(Booking.objects.filter(status="booked").count(), 2)

    def test_concurrent_identical_create_returns_one_booking(self):
        barrier, request_id = Barrier(2), uuid.uuid4()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.reserve, self.tokens[0], request_id, barrier) for _ in range(2)]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(sorted(status for status, _ in results), [200, 201])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(Booking.objects.filter(status="booked").count(), 2)


@skipUnless(connection.vendor == "postgresql", "Concurrency requires PostgreSQL row locks")
@override_settings(MOBILE_PUSH_SENDER="test.gateway")
class MobilePushConcurrencyTests(TransactionTestCase):
    def test_two_workers_claim_each_delivery_only_once(self):
        import hashlib
        customer = CustomerProfile.objects.create(
            user=User.objects.create_user(username="push-concurrent"), phone="+77000002009",
        )
        issue_tokens(customer)
        MobilePushDevice.objects.create(
            id=uuid.uuid4(), customer=customer, session=MobileRefreshSession.objects.get(customer=customer),
            platform="android", token="test-token", token_hash=hashlib.sha256(b"test-token").hexdigest(),
        )
        MobileNotification.objects.create(customer=customer, type="booking.changed")
        barrier = Barrier(2)

        def work():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return deliver_pending(1)
            finally:
                close_old_connections()

        with patch("mobile_api.push.import_string") as loader:
            loader.return_value.return_value = True
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(work) for _ in range(2)]
                counts = [future.result(timeout=30) for future in futures]
            self.assertEqual(loader.return_value.call_count, 1)
        self.assertEqual(sum(item["delivered"] for item in counts), 1)
        self.assertEqual(MobilePushDelivery.objects.get().state, "delivered")
