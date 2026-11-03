import hashlib
import uuid
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from common_api.models import PartnerProfile, SubscriptionPlan
from partner_api.models import Booking
from .booking_contract import claim_unowned_bookings, owned_bookings
from .models import (
    CustomerProfile, CustomerSubscription, MobileDeletionReceipt, MobileNotification,
    MobileBookingRecord, MobilePushDelivery, MobilePushDevice, MobileRefreshSession, NotificationPreferences,
)
from .push import PushDeliveryError, PushTokenInvalid, deliver_pending
from .views import issue_tokens


class AccountFixture(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = CustomerProfile.objects.create(
            user=User.objects.create_user(username="release-account", first_name="Client"),
            phone="+77000003001",
        )
        self.tokens = issue_tokens(self.customer)
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.tokens['access_token']}"}

    def other_account(self):
        customer = CustomerProfile.objects.create(
            user=User.objects.create_user(username="release-other"), phone="+77000003002",
        )
        tokens = issue_tokens(customer)
        return customer, {"HTTP_AUTHORIZATION": f"Bearer {tokens['access_token']}"}


@override_settings(MOBILE_PUSH_SENDER="test.gateway")
class PushLifecycleTests(AccountFixture):
    def setUp(self):
        super().setUp()
        self.device_id = uuid.uuid4()
        self.url = f"/api/v1/mobile/notifications/devices/{self.device_id}/"

    def register(self, headers=None, token="registration-token"):
        return self.client.put(self.url, {"platform": "android", "token": token},
                               format="json", **(headers or self.headers))

    def notify(self):
        return MobileNotification.objects.create(customer=self.customer, type="booking.changed")

    def deliver(self, result=True, failure=None):
        with patch("mobile_api.push.import_string") as loader:
            sender = loader.return_value
            sender.return_value = result
            sender.side_effect = failure
            counts = deliver_pending(100)
            return counts, sender

    def test_registration_rotation_and_readback_do_not_expose_token(self):
        first = self.register()
        self.assertEqual(first.status_code, 200)
        self.assertNotIn("token", first.data)
        self.assertEqual(self.register(token="replacement-token").status_code, 200)
        self.assertEqual(MobilePushDevice.objects.count(), 1)
        self.assertEqual(MobilePushDevice.objects.get().token_hash,
                         hashlib.sha256(b"replacement-token").hexdigest())
        self.assertEqual(first["Cache-Control"], "no-store")

    @override_settings(MOBILE_PUSH_SENDER="")
    def test_unconfigured_push_is_explicitly_disabled(self):
        self.assertEqual(self.register().status_code, 503)
        self.assertFalse(self.client.get("/api/v1/mobile/config/").data["features"]["push"])
        self.notify()
        self.assertFalse(MobilePushDelivery.objects.exists())
        with self.assertRaisesMessage(CommandError, "not configured"):
            call_command("send_mobile_push", stdout=StringIO())

    def test_invalid_token_and_foreign_session_cannot_unregister(self):
        self.assertEqual(self.register(token="bad token").status_code, 400)
        self.register()
        _, foreign_headers = self.other_account()
        self.assertEqual(self.client.delete(self.url, **foreign_headers).status_code, 204)
        self.assertTrue(MobilePushDevice.objects.get().is_active)
        other_session = issue_tokens(self.customer)
        self.client.delete(self.url, HTTP_AUTHORIZATION=f"Bearer {other_session['access_token']}")
        self.assertTrue(MobilePushDevice.objects.get().is_active)
        self.client.delete(self.url, **self.headers)
        self.assertFalse(MobilePushDevice.objects.get().is_active)

    def test_foreign_installation_cannot_be_overwritten_with_another_token(self):
        self.register()
        _, foreign_headers = self.other_account()
        self.assertEqual(self.register(headers=foreign_headers, token="foreign-token").status_code, 409)
        other_url = f"/api/v1/mobile/notifications/devices/{uuid.uuid4()}/"
        response = self.client.put(other_url, {"platform": "ios", "token": "registration-token"},
                                   format="json", **foreign_headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(MobilePushDevice.objects.get().customer_id, self.customer.id)

    def test_account_switch_drops_previous_accounts_queued_push(self):
        self.register()
        self.notify()
        other, headers = self.other_account()
        self.assertEqual(self.register(headers=headers).status_code, 200)
        self.assertEqual(MobilePushDevice.objects.get().customer_id, other.id)
        counts, sender = self.deliver()
        self.assertEqual(counts["skipped"], 1)
        sender.assert_not_called()

    def test_notification_enqueue_and_gateway_acknowledgement_are_repeat_safe(self):
        self.register()
        notification = self.notify()
        notification.save()
        self.assertEqual(MobilePushDelivery.objects.count(), 1)
        counts, sender = self.deliver()
        self.assertEqual(counts["delivered"], 1)
        self.assertEqual(sender.call_args.kwargs["data"], {"type": "inbox.updated"})
        self.assertEqual(sender.call_args.kwargs["delivery_id"], str(MobilePushDelivery.objects.get().id))
        self.assertIsNotNone(MobilePushDelivery.objects.get().sent_at)
        counts, sender = self.deliver()
        sender.assert_not_called()

    def test_notification_and_delivery_roll_back_together(self):
        self.register()
        with self.assertRaisesMessage(ValueError, "rollback"):
            with transaction.atomic():
                self.notify()
                raise ValueError("rollback")
        self.assertFalse(MobileNotification.objects.exists())
        self.assertFalse(MobilePushDelivery.objects.exists())

    def test_refresh_transfers_device_without_losing_queued_push(self):
        self.register()
        self.notify()
        old_session = MobilePushDevice.objects.get().session_id
        response = self.client.post("/api/v1/mobile/auth/refresh/",
                                    {"refresh_token": self.tokens["refresh_token"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(MobilePushDevice.objects.get().session_id, old_session)
        self.assertEqual(self.deliver()[0]["delivered"], 1)

    def test_logout_disables_registration_and_pending_delivery(self):
        self.register()
        self.notify()
        self.assertEqual(self.client.post("/api/v1/mobile/auth/logout/", {}, format="json",
                                          **self.headers).status_code, 204)
        self.assertFalse(MobilePushDevice.objects.get().is_active)
        counts, sender = self.deliver()
        self.assertEqual(counts["skipped"], 1)
        sender.assert_not_called()

    def test_logout_all_devices_disables_every_session(self):
        self.register()
        other_tokens = issue_tokens(self.customer)
        self.client.put(f"/api/v1/mobile/notifications/devices/{uuid.uuid4()}/",
                        {"platform": "ios", "token": "second-device"}, format="json",
                        HTTP_AUTHORIZATION=f"Bearer {other_tokens['access_token']}")
        self.client.post("/api/v1/mobile/auth/logout/", {"all_devices": True},
                         format="json", **self.headers)
        self.assertFalse(MobilePushDevice.objects.filter(is_active=True).exists())

    def test_phone_change_disables_other_devices_but_keeps_current_one(self):
        self.register()
        other_tokens = issue_tokens(self.customer)
        self.client.put(f"/api/v1/mobile/notifications/devices/{uuid.uuid4()}/",
                        {"platform": "ios", "token": "second-device"}, format="json",
                        HTTP_AUTHORIZATION=f"Bearer {other_tokens['access_token']}")
        phone = "+77000003003"
        self.assertEqual(self.client.post("/api/v1/mobile/users/me/phone/request/",
                                          {"phone": phone}, format="json", **self.headers).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/mobile/users/me/phone/confirm/",
                                          {"phone": phone, "code": "11111"},
                                          format="json", **self.headers).status_code, 200)
        self.assertEqual(MobilePushDevice.objects.filter(is_active=True).count(), 1)
        self.assertTrue(MobilePushDevice.objects.get(id=self.device_id).is_active)

    def test_preferences_gate_queue_and_are_rechecked_before_send(self):
        self.register()
        preferences = NotificationPreferences.objects.create(customer=self.customer, bookings_enabled=False)
        self.notify()
        self.assertFalse(MobilePushDelivery.objects.exists())
        preferences.bookings_enabled = True
        preferences.save()
        self.notify()
        preferences.delivery_enabled = False
        preferences.save()
        counts, sender = self.deliver()
        self.assertEqual(counts["skipped"], 1)
        sender.assert_not_called()
        self.assertEqual(self.customer.notifications.count(), 2)

    def test_expired_session_is_not_delivered(self):
        self.register()
        self.notify()
        MobileRefreshSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        counts, sender = self.deliver()
        self.assertEqual(counts["skipped"], 1)
        sender.assert_not_called()

    def test_transient_failure_retries_without_logging_token(self):
        self.register()
        self.notify()
        with self.assertLogs("mobile_api.push", level="WARNING") as logs:
            counts, _ = self.deliver(failure=PushDeliveryError("secret must not appear"))
        self.assertEqual(counts["retry"], 1)
        item = MobilePushDelivery.objects.get()
        self.assertEqual(item.attempts, 1)
        self.assertEqual(item.state, "pending")
        self.assertGreater(item.available_at, timezone.now())
        self.assertNotIn("secret", "".join(logs.output))
        self.assertNotIn("registration-token", "".join(logs.output))
        self.assertEqual(self.deliver()[0]["delivered"], 0)

    def test_false_acknowledgement_eventually_fails_after_five_attempts(self):
        self.register()
        self.notify()
        with self.assertLogs("mobile_api.push", level="WARNING"):
            for attempt in range(5):
                MobilePushDelivery.objects.update(available_at=timezone.now() - timedelta(seconds=1))
                counts, _ = self.deliver(result=None)
                self.assertEqual(counts["failed"] if attempt == 4 else counts["retry"], 1)
        self.assertEqual(MobilePushDelivery.objects.get().state, "failed")

    def test_invalid_gateway_token_is_disabled_permanently(self):
        self.register()
        self.notify()
        with self.assertLogs("mobile_api.push", level="WARNING"):
            counts, _ = self.deliver(failure=PushTokenInvalid())
        self.assertEqual(counts["failed"], 1)
        self.assertFalse(MobilePushDevice.objects.get().is_active)

    def test_unexpected_gateway_exception_is_not_hidden_as_success(self):
        self.register()
        self.notify()
        with self.assertRaisesMessage(RuntimeError, "adapter bug"):
            self.deliver(failure=RuntimeError("adapter bug"))
        self.assertEqual(MobilePushDelivery.objects.get().state, "pending")

    def test_worker_validates_bounds_and_reports_counts(self):
        with self.assertRaisesMessage(CommandError, "--limit"):
            call_command("send_mobile_push", limit=0, stdout=StringIO())
        output = StringIO()
        with patch("mobile_api.push.import_string"):
            call_command("send_mobile_push", limit=1, stdout=output)
        self.assertIn("delivered=0", output.getvalue())

    def test_watch_worker_runs_bounded_batches_without_claiming_an_empty_delivery(self):
        output = StringIO()
        with patch("mobile_api.management.commands.send_mobile_push.deliver_pending") as deliver, patch(
            "mobile_api.management.commands.send_mobile_push.time.sleep", side_effect=KeyboardInterrupt,
        ) as sleep:
            deliver.return_value = {"delivered": 0, "skipped": 0, "failed": 0, "retry": 0}
            with self.assertRaises(KeyboardInterrupt):
                call_command("send_mobile_push", limit=20, watch=True, stdout=output)
            deliver.assert_called_once_with(20)
            sleep.assert_called_once_with(10)
        self.assertEqual(output.getvalue(), "")


class SubscriptionReadbackTests(AccountFixture):
    def test_openapi_covers_release_endpoints_and_deletion_header(self):
        from drf_spectacular.validation import validate_schema
        response = self.client.get("/api/v1/mobile/schema/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        validate_schema(response.data)
        paths = response.data["paths"]
        for path, method in (
            ("subscriptions/current/", "get"), ("users/me/deletion-request/", "post"),
            ("notifications/devices/{device_id}/", "put"), ("notifications/devices/{device_id}/", "delete"),
        ):
            operation = paths[f"/api/v1/mobile/{path}"][method]
            self.assertEqual(operation["security"], [{"MobileBearer": []}])
            self.assertIn("401", operation["responses"])
        parameters = paths["/api/v1/mobile/users/me/"]["delete"]["parameters"]
        self.assertTrue(any(item["name"] == "X-Deletion-Receipt" and item["in"] == "header" for item in parameters))
        self.assertIn("/api/v1/mobile/auth/deletion-status/", paths)
        self.assertIn("/api/v1/mobile/subscriptions/plans/", paths)

    def test_plans_are_actual_non_archived_data_not_checkout_quotes(self):
        plan = SubscriptionPlan.objects.create(name="Configured plan", monthly_price=3000, duration_months=3)
        SubscriptionPlan.objects.create(name="Hidden", monthly_price=100, is_archived=True)
        response = self.client.get("/api/v1/mobile/subscriptions/plans/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"][0]["id"], plan.id)
        self.assertEqual(response.data["data"][0]["monthly_price"], "3000.00")
        self.assertEqual(len(response.data["data"]), 1)
        self.assertFalse(response.data["checkout_available"])
        self.assertFalse(response.data["price_is_checkout_quote"])

    def test_absent_active_expired_paused_and_inclusive_expiry(self):
        url = "/api/v1/mobile/subscriptions/current/"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, **self.headers).data["status"], "absent")
        item = CustomerSubscription.objects.create(customer=self.customer, expires_at=timezone.localdate())
        response = self.client.get(url, **self.headers)
        self.assertTrue(response.data["is_active"])
        self.assertEqual(response.data["status"], "active")
        item.status = CustomerSubscription.Status.PAUSED
        item.save()
        self.assertFalse(self.client.get(url, **self.headers).data["is_active"])
        self.assertEqual(self.client.get(url, **self.headers).data["status"], "paused")
        item.expires_at = timezone.localdate() - timedelta(days=1)
        item.save()
        self.assertEqual(self.client.get(url, **self.headers).data["status"], "expired")
        item.expires_at = None
        item.status = CustomerSubscription.Status.ACTIVE
        item.save()
        self.assertTrue(self.client.get(url, **self.headers).data["is_active"])

    def test_subscription_is_account_scoped_and_cannot_be_activated_by_client(self):
        CustomerSubscription.objects.create(customer=self.customer, plan_name="Private plan")
        _, headers = self.other_account()
        response = self.client.get("/api/v1/mobile/subscriptions/current/", **headers)
        self.assertEqual(response.data["status"], "absent")
        self.assertIsNone(response.data["plan_name"])
        self.assertEqual(self.client.post("/api/v1/mobile/subscriptions/current/",
                                          {"status": "active"}, format="json", **headers).status_code, 405)


class DeletionReconciliationTests(AccountFixture):
    request_url = "/api/v1/mobile/users/me/deletion-request/"
    status_url = "/api/v1/mobile/auth/deletion-status/"

    def prepare(self):
        response = self.client.post(self.request_url, {}, format="json", **self.headers)
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["deletion_ui_ready"])
        return response.data["receipt"]

    def status(self, receipt):
        return self.client.post(self.status_url, {"receipt": receipt}, format="json")

    def test_receipt_confirms_deletion_without_the_revoked_session(self):
        receipt = self.prepare()
        stored = MobileDeletionReceipt.objects.get()
        self.assertNotIn(receipt.split(".")[1], stored.secret_hash)
        self.assertEqual(self.status(receipt).data["state"], "requested")
        response = self.client.delete("/api/v1/mobile/users/me/", HTTP_X_DELETION_RECEIPT=receipt, **self.headers)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(CustomerProfile.objects.filter(pk=self.customer.id).exists())
        result = self.status(receipt)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["state"], "deleted")
        self.assertIsNotNone(result.data["completed_at"])
        self.assertEqual(result["Cache-Control"], "no-store")
        self.assertEqual(self.status(receipt).data, result.data)
        self.assertEqual(self.client.get("/api/v1/mobile/users/me/", **self.headers).status_code, 401)
        stored.refresh_from_db()
        self.assertIsNone(stored.customer_id)
        self.assertIsNone(stored.session_id)

    def test_invalid_expired_and_foreign_receipts_do_not_delete_account(self):
        receipt = self.prepare()
        self.assertEqual(self.status("bad").status_code, 404)
        self.assertEqual(self.status(receipt[:-1] + "!").status_code, 404)
        _, other_headers = self.other_account()
        self.assertEqual(self.client.delete("/api/v1/mobile/users/me/", HTTP_X_DELETION_RECEIPT=receipt,
                                            **other_headers).status_code, 409)
        MobileDeletionReceipt.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.status(receipt).status_code, 404)
        self.assertEqual(self.client.delete("/api/v1/mobile/users/me/", HTTP_X_DELETION_RECEIPT=receipt,
                                            **self.headers).status_code, 409)
        self.assertEqual(CustomerProfile.objects.count(), 2)

    def test_failed_delete_does_not_confirm_success(self):
        receipt = self.prepare()
        with patch.object(User, "delete", side_effect=DatabaseError("test rollback")):
            with self.assertLogs("django.request", level="ERROR"), self.assertRaises(DatabaseError):
                self.client.delete("/api/v1/mobile/users/me/", HTTP_X_DELETION_RECEIPT=receipt, **self.headers)
        self.assertEqual(self.status(receipt).data["state"], "requested")
        self.assertTrue(CustomerProfile.objects.filter(pk=self.customer.id).exists())

    def test_legacy_delete_also_completes_prepared_receipts(self):
        receipt = self.prepare()
        self.assertEqual(self.client.delete("/api/v1/mobile/users/me/", **self.headers).status_code, 204)
        self.assertEqual(self.status(receipt).data["state"], "deleted")

    def test_receipt_survives_refresh_but_cannot_be_used_by_another_session(self):
        receipt = self.prepare()
        second = issue_tokens(self.customer)
        self.assertEqual(self.client.delete("/api/v1/mobile/users/me/", HTTP_X_DELETION_RECEIPT=receipt,
                                            HTTP_AUTHORIZATION=f"Bearer {second['access_token']}").status_code, 409)
        response = self.client.post("/api/v1/mobile/auth/refresh/",
                                    {"refresh_token": self.tokens["refresh_token"]}, format="json")
        access = response.data["tokens"]["access_token"]
        self.assertEqual(self.client.delete("/api/v1/mobile/users/me/", HTTP_X_DELETION_RECEIPT=receipt,
                                            HTTP_AUTHORIZATION=f"Bearer {access}").status_code, 204)
        self.assertEqual(self.status(receipt).data["state"], "deleted")

    def test_cleanup_removes_only_expired_receipts_not_accounts(self):
        first = self.prepare()
        second = self.prepare()
        MobileDeletionReceipt.objects.filter(id=first.split(".")[0]).update(expires_at=timezone.now() - timedelta(seconds=1))
        call_command("purge_mobile_deletion_receipts", stdout=StringIO())
        self.assertEqual(MobileDeletionReceipt.objects.count(), 1)
        self.assertEqual(self.status(second).status_code, 200)
        self.assertTrue(CustomerProfile.objects.filter(pk=self.customer.id).exists())

    def test_deletion_tombstones_legacy_booking_before_phone_can_be_reused(self):
        partner = PartnerProfile.objects.create(
            user=User.objects.create_user(username="legacy-owner-partner"), phone="+77000003009",
        )
        booking = Booking.objects.create(
            tenant_slug="public", partner_profile=partner, client_name="Previous owner",
            client_phone=self.customer.phone, starts_at=timezone.now() + timedelta(days=1),
        )
        MobileBookingRecord.objects.filter(booking=booking).delete()
        receipt = self.prepare()
        self.assertEqual(self.client.delete("/api/v1/mobile/users/me/", HTTP_X_DELETION_RECEIPT=receipt,
                                            **self.headers).status_code, 204)
        self.assertTrue(MobileBookingRecord.objects.filter(booking=booking, owner_claimed=True,
                                                          customer__isnull=True).exists())
        replacement = CustomerProfile.objects.create(
            user=User.objects.create_user(username="recycled-phone"), phone=self.customer.phone,
        )
        claim_unowned_bookings(replacement)
        self.assertFalse(owned_bookings(replacement).filter(pk=booking.id).exists())
