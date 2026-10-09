from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from decimal import Decimal
from threading import Barrier

from django.contrib.auth.models import User
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from common_api.models import PartnerProfile
from mobile_api.models import CustomerProfile, CustomerSubscription
from .models import Booking, Category, Service, ServiceKind, Specialist


class LifecycleFixture:
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.email = "launch-partner@example.com"
        self.password = "Launch-test-2026!"
        self.admin = User.objects.create_user(
            username="launch-admin", password=self.password, is_staff=True,
        )
        login = self.client.post(
            "/api/v1/common/admin/login/",
            {"username": self.admin.username, "password": self.password}, format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.admin_headers = {"HTTP_AUTHORIZATION": f"Bearer {login.data['token']}"}
        category = self.client.post(
            "/api/v1/common/admin/subscriptions/",
            {"resource": "categories", "name": "Launch courses", "allows_group_services": True},
            format="json", **self.admin_headers,
        )
        self.assertEqual(category.status_code, 201)
        self.category = Category.objects.get(tenant_slug="public", name="Launch courses")
        self.kind = ServiceKind.objects.create(
            tenant_slug="public", category=self.category, name="Launch training",
        )
        registration = self.client.post(
            "/api/v1/common/auth/register/",
            {
                "full_name": "Launch owner", "phone": "+77009990001", "email": self.email,
                "password": self.password, "business_category": self.category.name,
                "company_name": "Launch CRM studio", "address": "Test address",
            }, format="json",
        )
        self.assertEqual(registration.status_code, 201)
        self.partner = PartnerProfile.objects.get(user__email=self.email)
        self.headers = {"HTTP_X_PARTNER_EMAIL": self.email, "HTTP_X_TENANT": "public"}
        login = self.client.post(
            "/api/v1/common/auth/login/",
            {"username": self.email, "password": self.password}, format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data["user"]["user_type"], "partner")
        self.service = self.create_service("Launch group", "group")
        self.individual = self.create_service("Launch individual", "individual")
        self.visit_date = timezone.localdate() + timedelta(days=7)
        self.starts_at = timezone.make_aware(datetime.combine(self.visit_date, time(10)))
        self.schedule = [{
            "day": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][self.visit_date.weekday()],
            "is_day_off": False, "start_time": "09:00", "end_time": "18:00",
            "breaks": [{"start_time": "13:00", "end_time": "14:00"}],
            "discount_windows": [
                {"start_time": "10:00", "end_time": "12:00"},
                {"start_time": "15:00", "end_time": "17:00"},
            ],
        }]
        specialist = self.client.post(
            "/api/v1/partner/specialists/",
            {
                "full_name": "Launch Anna", "phone": "+77009990002",
                "service_ids": [self.service.id, self.individual.id],
                "working_schedule": self.schedule,
            }, format="json", **self.headers,
        )
        self.assertEqual(specialist.status_code, 201)
        self.specialist = Specialist.objects.get(id=specialist.data["id"])
        self.customer = CustomerProfile.objects.create(
            user=User.objects.create_user(username="launch-customer"),
            phone="+77009990003",
        )
        self.subscription = CustomerSubscription.objects.create(
            customer=self.customer, expires_at=self.visit_date,
        )

    def create_service(self, name, service_type):
        response = self.client.post(
            "/api/v1/partner/services/",
            {
                "name": name, "category": self.category.id, "kind": self.kind.id,
                "service_type": service_type, "details": {"min_people": 1, "max_people": 2},
                "price": "10000.00", "duration_minutes": 60, "discount_percent": 20,
                "is_subscription": True,
            }, format="json", **self.headers,
        )
        self.assertEqual(response.status_code, 201)
        return Service.objects.get(id=response.data["id"])

    def book(self, phone=None, starts_at=None, service=None, **extra):
        service = service or self.service
        return self.client.post(
            "/api/v1/partner/bookings/",
            {
                "service_ids": [service.id], "service_name": service.name,
                "manager_name": self.specialist.full_name,
                "starts_at": (starts_at or self.starts_at).isoformat(),
                "client_name": "Launch customer", "client_phone": phone or self.customer.phone,
                **extra,
            }, format="json", **self.headers,
        )

    def slots(self):
        response = self.client.get(
            f"/api/v1/mobile/catalog/partners/{self.partner.id}/specialists/{self.specialist.id}/availability/",
            {"date": self.visit_date.isoformat(), "service_id": self.service.id},
        )
        self.assertEqual(response.status_code, 200)
        return response.data["slots"]


class CrmLifecycleTests(LifecycleFixture, TestCase):
    def test_editing_legacy_unpriced_service_preserves_null_price(self):
        self.individual.price = None
        self.individual.save(update_fields=["price"])
        response = self.client.patch(
            f"/api/v1/partner/services/{self.individual.id}/",
            {"description": "Updated description"}, format="json", **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.individual.refresh_from_db()
        self.assertIsNone(self.individual.price)

    def test_registration_profile_and_catalog(self):
        duplicate = self.client.post(
            "/api/v1/common/auth/register/",
            {"full_name": "Duplicate", "phone": "+77009990001", "email": self.email, "password": self.password},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 409)
        update = self.client.patch(
            "/api/v1/partner/profile/",
            {"city": "Almaty", "description": "Launch test studio"},
            format="json", **self.headers,
        )
        self.assertEqual(update.status_code, 200)
        self.partner.refresh_from_db()
        self.assertEqual(self.partner.city, "Almaty")
        catalog = self.client.get("/api/v1/mobile/catalog/partners/", {"search": "Launch CRM"})
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual([p["id"] for p in catalog.data["data"]], [self.partner.id])
        listed = self.client.get("/api/v1/partner/services/", **self.headers)
        self.assertEqual({s["id"] for s in listed.data}, {self.service.id, self.individual.id})

    def test_subscription_and_discount_window_matrix(self):
        for status, expiry, hour, expected in [
            ("active", self.visit_date, 10, "8000.00"),
            ("active", self.visit_date, 9, "10000.00"),
            ("active", self.visit_date, 12, "10000.00"),
            ("active", self.visit_date, 15, "8000.00"),
            ("active", self.visit_date - timedelta(days=1), 10, "10000.00"),
            ("paused", self.visit_date, 10, "10000.00"),
            ("active", None, 10, "8000.00"),
        ]:
            with self.subTest(status=status, expiry=expiry, hour=hour):
                self.subscription.status = status
                self.subscription.expires_at = expiry
                self.subscription.save()
                created = self.book(starts_at=self.starts_at.replace(hour=hour))
                self.assertEqual(created.status_code, 201)
                self.assertEqual(created.data["final_price"], expected)
                Booking.objects.get(id=created.data["id"]).delete()
        self.subscription.delete()
        created = self.book()
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["final_price"], "10000.00")

    def test_full_group_cancel_rebook_complete_and_customer_history(self):
        first = self.book()
        second = self.book(phone="+77009990004")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data["group_session"]["occupied_places"], 2)
        self.assertEqual(second.data["group_session"]["available_places"], 0)
        self.assertEqual([p["final_price"] for p in second.data["group_session"]["participants"]], ["8000.00", "10000.00"])
        self.assertNotIn("10:00", self.slots())
        self.assertEqual(self.book(phone="+77009990005").status_code, 409)
        cancelled = self.client.patch(
            f"/api/v1/partner/bookings/{second.data['id']}/",
            {"status": "cancelled"}, format="json", **self.headers,
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertIn("10:00", self.slots())
        replacement = self.book(phone="+77009990005")
        self.assertEqual(replacement.status_code, 201)
        completed = self.client.patch(
            f"/api/v1/partner/bookings/{first.data['id']}/",
            {"group_action": "complete", "participant_ids": [first.data["id"]]},
            format="json", **self.headers,
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(
            [(p["id"], p["status"]) for p in completed.data["group_session"]["participants"]],
            [(first.data["id"], "completed"), (replacement.data["id"], "no_show")],
        )
        repeated = self.client.patch(
            f"/api/v1/partner/bookings/{first.data['id']}/",
            {"group_action": "complete", "participant_ids": [first.data["id"]]},
            format="json", **self.headers,
        )
        self.assertEqual(repeated.status_code, 409)
        Booking.objects.filter(id=first.data["id"]).update(client_phone="+7 (700) 999-00-03")
        history = self.client.get(
            f"/api/v1/common/admin/customers/{self.customer.id}/", **self.admin_headers,
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["visits"][0]["final_price"], "8000.00")
        dashboard = self.client.get("/api/v1/common/admin/dashboard/", **self.admin_headers)
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data["metrics"]["subscriptions_active"], 1)
        self.assertEqual(Decimal(dashboard.data["metrics"]["customers_turnover"]), Decimal("8000.00"))
        customer = next(c for c in dashboard.data["customers"] if c["id"] == self.customer.id)
        self.assertTrue(customer["subscription_active"])
        self.assertEqual(customer["visits"], 1)

    def test_duplicate_formatted_phone_and_shifted_group_conflicts(self):
        self.assertEqual(self.book().status_code, 201)
        self.assertEqual(self.book(phone="+7 (700) 999-00-03").status_code, 409)
        self.assertEqual(self.book(phone="+77009990004", starts_at=self.starts_at + timedelta(minutes=30)).status_code, 409)
        self.assertEqual(self.book(phone="+77009990004", service=self.individual).status_code, 409)
        self.assertEqual(self.book(phone="+77009990004", starts_at=self.starts_at + timedelta(hours=1)).status_code, 201)

    def test_individual_service_allows_only_one_customer(self):
        self.assertEqual(self.book(service=self.individual).status_code, 201)
        self.assertEqual(self.book(phone="+77009990004", service=self.individual).status_code, 409)

    def test_break_work_boundaries_day_off_and_partial_discount_window(self):
        slots = self.slots()
        self.assertIn("09:00", slots)
        self.assertIn("10:00", slots)
        self.assertIn("12:00", slots)
        self.assertNotIn("12:30", slots)
        self.assertNotIn("13:00", slots)
        self.assertIn("14:00", slots)
        self.assertIn("17:00", slots)
        self.assertNotIn("17:30", slots)
        for hour, minute in [(8, 30), (12, 30), (13, 0), (17, 30)]:
            with self.subTest(hour=hour, minute=minute):
                self.assertEqual(self.book(starts_at=self.starts_at.replace(hour=hour, minute=minute)).status_code, 409)
        partial = self.book(starts_at=self.starts_at.replace(hour=11, minute=30))
        self.assertEqual(partial.status_code, 201)
        self.assertEqual(partial.data["final_price"], "10000.00")
        next_day = self.starts_at + timedelta(days=1)
        self.assertEqual(self.book(starts_at=next_day).status_code, 409)

    def test_move_reprices_and_service_edits_preserve_snapshot(self):
        booking = self.book()
        self.assertEqual(booking.status_code, 201)
        url = f"/api/v1/partner/bookings/{booking.data['id']}/"
        move = self.client.patch(
            url, {"starts_at": self.starts_at.replace(hour=9).isoformat()}, format="json", **self.headers,
        )
        self.assertEqual(move.status_code, 200)
        self.assertEqual(move.data["final_price"], "10000.00")
        moved_back = self.client.patch(
            url, {"starts_at": self.starts_at.isoformat()}, format="json", **self.headers,
        )
        self.assertEqual(moved_back.status_code, 200)
        self.assertEqual(moved_back.data["final_price"], "8000.00")
        edit_price = self.client.patch(
            f"/api/v1/partner/services/{self.service.id}/", {"price": "20000.00"},
            format="json", **self.headers,
        )
        self.assertEqual(edit_price.status_code, 200)
        completed = self.client.patch(url, {"status": "completed"}, format="json", **self.headers)
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data["final_price"], "8000.00")

    def test_no_show_only_affects_selected_participants(self):
        first, second = self.book(), self.book(phone="+77009990004")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        response = self.client.patch(
            f"/api/v1/partner/bookings/{first.data['id']}/",
            {"group_action": "no_show", "participant_ids": [second.data["id"]]},
            format="json", **self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p["status"] for p in response.data["group_session"]["participants"]], ["booked", "no_show"])

    def test_foreign_partner_cannot_modify_booking(self):
        created = self.book()
        self.assertEqual(created.status_code, 201)
        user = User.objects.create_user(username="other-launch@example.com")
        PartnerProfile.objects.create(user=user, business_category=self.category.name)
        response = self.client.patch(
            f"/api/v1/partner/bookings/{created.data['id']}/",
            {"status": "completed"}, format="json",
            HTTP_X_PARTNER_EMAIL=user.username, HTTP_X_TENANT="public",
        )
        self.assertEqual(response.status_code, 404)

    def test_group_capacity_and_category_cannot_be_disabled_with_bookings(self):
        first, second = self.book(), self.book(phone="+77009990004")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        service_url = f"/api/v1/partner/services/{self.service.id}/"
        for payload in (
            {"details": {"min_people": 1, "max_people": 1}},
            {"service_type": "individual"},
            {"duration_minutes": 90},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.patch(service_url, payload, format="json", **self.headers).status_code, 409)

    def test_inactive_service_cannot_be_booked(self):
        self.service.is_active = False
        self.service.save()
        self.assertEqual(self.book().status_code, 400)

    def test_invalid_booking_status_is_rejected(self):
        response = self.book(status="invented")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_past_booking_is_rejected(self):
        self.assertEqual(self.book(starts_at=self.starts_at - timedelta(days=14)).status_code, 400)

    def test_browser_timestamp_without_offset_creates_and_moves_booking(self):
        created = self.book(starts_at=self.starts_at.replace(tzinfo=None))
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["starts_at"], self.starts_at.isoformat())
        moved = self.client.patch(
            f"/api/v1/partner/bookings/{created.data['id']}/",
            {"starts_at": self.starts_at.replace(hour=11, tzinfo=None).isoformat()},
            format="json", **self.headers,
        )
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(moved.data["starts_at"], self.starts_at.replace(hour=11).isoformat())

    def test_service_invalid_numbers_are_rejected_on_create_and_edit(self):
        base = {
            "name": "Invalid service", "category": self.category.id, "kind": self.kind.id,
            "price": "10000.00", "duration_minutes": 60, "discount_percent": 20,
        }
        for payload in [
            {"duration_minutes": "invalid"}, {"duration_minutes": 0},
            {"duration_minutes": -1}, {"price": "invalid"}, {"price": "-1.00"},
            {"price": "NaN"}, {"discount_percent": "invalid"}, {"discount_percent": 101},
        ]:
            with self.subTest(payload=payload):
                created = self.client.post("/api/v1/partner/services/", {**base, **payload}, format="json", **self.headers)
                self.assertEqual(created.status_code, 400)
                updated = self.client.patch(
                    f"/api/v1/partner/services/{self.service.id}/", payload, format="json", **self.headers,
                )
                self.assertEqual(updated.status_code, 400)

    def test_blocked_partner_cannot_continue_using_crm(self):
        blocked = self.client.post(
            f"/api/v1/common/admin/partners/{self.partner.id}/status/",
            {"is_active": False}, format="json", **self.admin_headers,
        )
        self.assertEqual(blocked.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/partner/bookings/", **self.headers).status_code, 403)
        self.assertEqual(self.book().status_code, 403)

    def test_booking_invalid_phone_status_and_past_move_are_rejected(self):
        self.assertEqual(self.book(phone="+7").status_code, 400)
        booking = self.book()
        self.assertEqual(booking.status_code, 201)
        for payload in [
            {"status": "invented"},
            {"starts_at": (self.starts_at - timedelta(days=14)).isoformat()},
            {"client_phone": "invalid"},
        ]:
            with self.subTest(payload=payload):
                updated = self.client.patch(
                    f"/api/v1/partner/bookings/{booking.data['id']}/", payload,
                    format="json", **self.headers,
                )
                self.assertEqual(updated.status_code, 400)
        booking_model = Booking.objects.get(id=booking.data["id"])
        self.assertEqual(booking_model.starts_at, self.starts_at)
        self.assertEqual(booking_model.status, "booked")

    def test_specialist_invalid_service_edit_is_atomic(self):
        response = self.client.patch(
            f"/api/v1/partner/specialists/{self.specialist.id}/",
            {"full_name": "Should not persist", "service_ids": [999999]},
            format="json", **self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.specialist.refresh_from_db()
        self.assertEqual(self.specialist.full_name, "Launch Anna")


@override_settings(MOBILE_SMS_TEST_CODE="11111", MOBILE_JWT_ACCESS_TTL_SECONDS=3600, MOBILE_JWT_REFRESH_TTL_SECONDS=2592000)
class CrmMobileLifecycleTests(LifecycleFixture, TestCase):
    def test_mobile_customer_registration_subscription_booking_cancel_and_completion(self):
        mobile = APIClient()
        registered = mobile.post(
            "/api/v1/mobile/auth/register/", {"phone": "+77009990006", "code": "11111"}, format="json",
        )
        self.assertEqual(registered.status_code, 201)
        mobile.credentials(HTTP_AUTHORIZATION=f"Bearer {registered.data['tokens']['access_token']}")
        profile = mobile.patch("/api/v1/mobile/users/me/", {"name": "Launch mobile customer"}, format="json")
        self.assertEqual(profile.status_code, 200)
        payload = {
            "partner_id": self.partner.id, "service_id": self.service.id,
            "specialist_id": self.specialist.id, "starts_at": self.starts_at.isoformat(),
        }
        created = mobile.post("/api/v1/mobile/bookings/", payload, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["final_price"], "10000.00")
        cancelled = mobile.post(f"/api/v1/mobile/bookings/{created.data['id']}/cancel/", {}, format="json")
        self.assertEqual(cancelled.status_code, 200)
        customer = CustomerProfile.objects.get(phone="+77009990006")
        CustomerSubscription.objects.create(customer=customer, expires_at=self.visit_date)
        subscribed = mobile.post("/api/v1/mobile/bookings/", payload, format="json")
        self.assertEqual(subscribed.status_code, 201)
        self.assertEqual(subscribed.data["final_price"], "8000.00")
        complete = self.client.patch(
            f"/api/v1/partner/bookings/{subscribed.data['id']}/",
            {"group_action": "complete", "participant_ids": [subscribed.data["id"]]},
            format="json", **self.headers,
        )
        self.assertEqual(complete.status_code, 200)
        history = mobile.get("/api/v1/mobile/bookings/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["data"][0]["status"], "completed")
        self.assertEqual(mobile.post(f"/api/v1/mobile/bookings/{subscribed.data['id']}/cancel/", {}, format="json").status_code, 409)


class CrmCapacityConcurrencyTests(LifecycleFixture, TransactionTestCase):
    def test_two_simultaneous_requests_cannot_take_last_group_place(self):
        self.assertEqual(self.book().status_code, 201)
        barrier = Barrier(2)

        def reserve(phone):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = APIClient().post(
                    "/api/v1/partner/bookings/",
                    {
                        "service_ids": [self.service.id], "service_name": self.service.name,
                        "manager_name": self.specialist.full_name, "starts_at": self.starts_at.isoformat(),
                        "client_name": "Concurrent customer", "client_phone": phone,
                    }, format="json", **self.headers,
                )
                return response.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reserve, ["+77009990007", "+77009990008"]))
        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(Booking.objects.filter(status="booked").count(), 2)
