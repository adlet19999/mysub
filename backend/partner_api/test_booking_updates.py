import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory

from .models import Booking, BookingPass, Specialist
from .test_lifecycle import LifecycleFixture
from .views import BookingPassCreateView, calculate_booking_pricing


class BookingUpdateTests(LifecycleFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.individual.is_pass = True
        self.individual.visit_count = 3
        self.individual.pass_price_mode = "total"
        self.individual.price = Decimal("100.00")
        self.individual.save()
        self.visits = [self.starts_at + timedelta(weeks=index) for index in range(3)]
        self.payload = {
            "request_id": str(uuid.uuid4()),
            "service_id": self.individual.id,
            "specialist_id": self.specialist.id,
            "client_name": "Pass customer",
            "client_phone": self.customer.phone,
            "visits": [value.isoformat() for value in self.visits],
        }

    def create_pass(self, **changes):
        return self.client.post("/api/v1/partner/bookings/passes/", {**self.payload, **changes}, format="json", **self.headers)

    def availability(self, service=None, **changes):
        return self.client.get("/api/v1/partner/bookings/availability/", {
            "date": self.visit_date.isoformat(),
            "service_ids": str((service or self.individual).id),
            "specialist_id": str(self.specialist.id),
            **changes,
        }, **self.headers)

    def test_pass_creates_all_visits_with_exact_total_and_persistent_link(self):
        response = self.create_pass()
        self.assertEqual(response.status_code, 201, response.data)
        visits = list(Booking.objects.order_by("visit_number"))
        self.assertEqual(len(visits), 3)
        self.assertEqual([item.final_price for item in visits], [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")])
        self.assertEqual(sum(item.final_price for item in visits), Decimal("100.00"))
        self.assertEqual(len({item.booking_pass_id for item in visits}), 1)
        self.assertEqual([item.starts_at for item in visits], self.visits)
        detail = response.data["items"][1]["booking_pass"]
        self.assertEqual(detail["visit_number"], 2)
        self.assertEqual(detail["visit_count"], 3)
        self.assertEqual(len(detail["visits"]), 3)
        self.assertTrue(all(item.booking_source == "manual" and item.discount_amount == 0 for item in visits))

    def test_per_visit_price_is_not_divided(self):
        self.individual.pass_price_mode = "per_visit"
        self.individual.save()
        response = self.create_pass()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["items"][0]["booking_pass"]["total_price"], "300.00")
        self.assertEqual([item["final_price"] for item in response.data["items"]], ["100.00"] * 3)

    def test_zero_price_and_large_package_totals_are_supported(self):
        for price in ("0.00", "9999999999.99"):
            with self.subTest(price=price):
                self.individual.price = Decimal(price)
                self.individual.pass_price_mode = "per_visit"
                self.individual.save()
                response = self.create_pass(request_id=str(uuid.uuid4()))
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(Decimal(response.data["items"][0]["booking_pass"]["total_price"]), Decimal(price) * 3)
                Booking.objects.all().delete()
                BookingPass.objects.all().delete()

    def test_retry_is_idempotent_and_changed_payload_is_rejected(self):
        first = self.create_pass()
        second = self.create_pass()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual([item["id"] for item in first.data["items"]], [item["id"] for item in second.data["items"]])
        self.assertEqual(Booking.objects.count(), 3)
        self.assertEqual(self.create_pass(client_name="Another name").status_code, 409)
        self.assertEqual(Booking.objects.count(), 3)

    def test_conflict_on_last_visit_creates_nothing(self):
        occupied = self.book(starts_at=self.visits[-1])
        self.assertEqual(occupied.status_code, 201)
        response = self.create_pass()
        self.assertEqual(response.status_code, 409)
        self.assertIn(self.visits[-1].strftime("%d.%m.%Y"), response.data["message"])
        self.assertEqual(BookingPass.objects.count(), 0)
        self.assertEqual(Booking.objects.count(), 1)

    def test_invalid_count_duplicate_overlap_past_and_break_dates_create_nothing(self):
        cases = [
            self.payload["visits"][:2],
            [self.visits[0].isoformat()] * 3,
            [self.visits[0].isoformat(), (self.visits[0] + timedelta(minutes=30)).isoformat(), self.visits[2].isoformat()],
            [(self.starts_at - timedelta(days=30)).isoformat(), *self.payload["visits"][1:]],
            [self.visits[0].replace(hour=12, minute=30).isoformat(), *self.payload["visits"][1:]],
        ]
        for visits in cases:
            with self.subTest(visits=visits):
                self.assertEqual(self.create_pass(visits=visits).status_code, 409)
                self.assertEqual(Booking.objects.count(), 0)
                self.assertEqual(BookingPass.objects.count(), 0)

    def test_malformed_dates_and_identifiers_are_reported(self):
        for changes in ({"visits": ["not-a-date"]}, {"visits": ["2099-02-30T10:00:00"]}, {"visits": [123]}, {"request_id": "bad"}, {"service_id": "bad"}, {"visits": None}):
            with self.subTest(changes=changes):
                self.assertEqual(self.create_pass(**changes).status_code, 400)

    def test_series_rolls_back_if_a_write_fails(self):
        original = Booking.objects.create
        calls = 0

        def fail_second(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Simulated write failure")
            return original(**kwargs)

        with patch.object(Booking.objects, "create", side_effect=fail_second):
            with self.assertRaisesMessage(RuntimeError, "Simulated write failure"):
                request = APIRequestFactory().post("/api/v1/partner/bookings/passes/", self.payload, format="json", **self.headers)
                BookingPassCreateView.as_view()(request)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(BookingPass.objects.count(), 0)

    def test_pass_settings_round_trip_and_do_not_replace_subscription_flag(self):
        response = self.client.get("/api/v1/partner/services/", **self.headers)
        service = next(item for item in response.data if item["id"] == self.individual.id)
        self.assertTrue(service["is_pass"])
        self.assertTrue(service["is_subscription"])
        self.assertEqual(service["visit_count"], 3)
        for count in (0, -1, 1.5, "3", True, 366):
            with self.subTest(count=count):
                response = self.client.patch(f"/api/v1/partner/services/{self.individual.id}/", {"visit_count": count}, format="json", **self.headers)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.book(service=self.individual).status_code, 400)

    def test_rescheduling_keeps_allocated_price_count_and_other_visits(self):
        response = self.create_pass()
        visit = response.data["items"][0]
        self.individual.price = Decimal("900.00")
        self.individual.visit_count = 8
        self.individual.save()
        moved = self.client.patch(f"/api/v1/partner/bookings/{visit['id']}/", {
            "starts_at": self.visits[0].replace(hour=11).isoformat(),
            "service_ids": [self.individual.id],
            "service_name": self.individual.name,
            "client_phone": self.customer.phone,
        }, format="json", **self.headers)
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual(moved.data["final_price"], "33.34")
        self.assertEqual(moved.data["booking_pass"]["visit_count"], 3)
        self.assertEqual(Booking.objects.get(visit_number=2).starts_at, self.visits[1])

    def test_cancellation_preserves_series_history_and_completed_visit_count(self):
        response = self.create_pass()
        first, second = response.data["items"][:2]
        completed = self.client.patch(f"/api/v1/partner/bookings/{first['id']}/", {"status": "completed"}, format="json", **self.headers)
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data["booking_pass"]["completed_visits"], 1)
        deleted = self.client.delete(f"/api/v1/partner/bookings/{second['id']}/", **self.headers)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(Booking.objects.get(id=second["id"]).status, "cancelled")
        self.assertEqual(Booking.objects.count(), 3)

    def test_availability_checks_both_ends_snapshot_duration_and_breaks(self):
        pricing = calculate_booking_pricing([self.individual], self.specialist, self.starts_at, allow_discount=False)
        pricing["pricing_details"][0]["duration_minutes"] = 90
        Booking.objects.create(tenant_slug="public", partner_profile=self.partner, manager_name=self.specialist.full_name, service_name=self.individual.name, starts_at=self.starts_at, client_name="Other client", client_phone="+77009998888", **pricing)
        response = self.availability()
        self.assertEqual(response.status_code, 200)
        self.assertIn("09:00", response.data["slots"])
        self.assertNotIn("09:15", response.data["slots"])
        self.assertNotIn("11:15", response.data["slots"])
        self.assertIn("11:30", response.data["slots"])
        self.assertNotIn("12:15", response.data["slots"])
        self.assertNotIn("17:15", response.data["slots"])
        self.individual.duration_minutes = 30
        self.individual.save()
        slots = self.availability().data["slots"]
        self.assertIn("09:30", slots)
        self.assertNotIn("09:45", slots)
        self.assertNotIn("11:15", slots)

    def test_availability_excludes_own_booking_but_checks_client_elsewhere(self):
        booked = self.book()
        self.assertEqual(booked.status_code, 201)
        group_slots = self.availability(service=self.service).data["slots"]
        self.assertIn("10:00", group_slots)
        personal = self.availability(service=self.service, client_phone=self.customer.phone).data["slots"]
        self.assertNotIn("10:00", personal)
        editing = self.availability(service=self.service, client_phone=self.customer.phone, exclude_booking_id=booked.data["id"])
        self.assertIn("10:00", editing.data["slots"])
        self.assertEqual(self.availability(exclude_booking_id=999999).status_code, 404)

    def test_group_capacity_and_completed_attendance_survive_reload(self):
        first, second = self.book(), self.book(phone="+77009990004")
        self.assertNotIn("10:00", self.availability(service=self.service).data["slots"])
        result = self.client.patch(f"/api/v1/partner/bookings/{first.data['id']}/", {
            "group_action": "complete", "participant_ids": [first.data["id"]],
        }, format="json", **self.headers)
        self.assertEqual(result.status_code, 200)
        reloaded = self.client.get("/api/v1/partner/bookings/", **self.headers)
        participants = next(item for item in reloaded.data if item["id"] == first.data["id"])["group_session"]["participants"]
        self.assertEqual({item["id"]: item["status"] for item in participants}, {first.data["id"]: "completed", second.data["id"]: "booked"})

    def test_shortened_working_hours_cannot_overlap_existing_visit(self):
        self.assertEqual(self.book().status_code, 201)
        schedule = [{**self.schedule[0], "end_time": "10:30", "breaks": [], "discount_windows": []}]
        response = self.client.patch(f"/api/v1/partner/specialists/{self.specialist.id}/", {"working_schedule": schedule}, format="json", **self.headers)
        self.assertEqual(response.status_code, 409, response.data)
        self.specialist.refresh_from_db()
        self.assertEqual(next(day for day in self.specialist.working_schedule if not day["is_day_off"])["end_time"], "18:00")

    def test_bulk_schedule_is_atomic_when_last_specialist_has_a_conflict(self):
        self.assertEqual(self.book().status_code, 201)
        other = Specialist.objects.create(tenant_slug="public", partner_profile=self.partner, full_name="Another specialist", working_schedule=self.schedule)
        response = self.client.patch("/api/v1/partner/specialists/schedule/", {"items": [
            {"specialist_id": other.id, "working_schedule": [{**self.schedule[0], "end_time": "17:00"}]},
            {"specialist_id": self.specialist.id, "working_schedule": [{**self.schedule[0], "end_time": "10:30", "breaks": [], "discount_windows": []}]},
        ]}, format="json", **self.headers)
        self.assertEqual(response.status_code, 409)
        other.refresh_from_db()
        self.assertEqual(other.working_schedule[0]["end_time"], "18:00")

    def test_bulk_schedule_updates_all_specialists_and_rejects_duplicate_or_foreign_ids(self):
        other = Specialist.objects.create(tenant_slug="public", partner_profile=self.partner, full_name="Another specialist", working_schedule=self.schedule)
        items = [{"specialist_id": item.id, "working_schedule": [{**self.schedule[0], "end_time": "17:00"}]} for item in (self.specialist, other)]
        response = self.client.patch("/api/v1/partner/specialists/schedule/", {"items": items}, format="json", **self.headers)
        self.assertEqual(response.status_code, 200, response.data)
        for item in (self.specialist, other):
            item.refresh_from_db()
            self.assertEqual(next(day for day in item.working_schedule if not day["is_day_off"])["end_time"], "17:00")
        for invalid_items in ([items[0], items[0]], [{"specialist_id": 999999, "working_schedule": self.schedule}]):
            response = self.client.patch("/api/v1/partner/specialists/schedule/", {"items": invalid_items}, format="json", **self.headers)
            self.assertEqual(response.status_code, 400)

    def test_enabling_pass_does_not_prevent_completion_of_existing_single_visit(self):
        self.service.is_pass = True
        self.service.visit_count = 2
        booked = Booking.objects.create(
            tenant_slug="public", partner_profile=self.partner, service_name=self.service.name,
            manager_name=self.specialist.full_name, client_name="Legacy customer", client_phone=self.customer.phone,
            starts_at=self.starts_at, **calculate_booking_pricing([self.service], self.specialist, self.starts_at, allow_discount=False),
        )
        self.service.save()
        response = self.client.patch(f"/api/v1/partner/bookings/{booked.id}/", {"status": "completed"}, format="json", **self.headers)
        self.assertEqual(response.status_code, 200, response.data)

    def test_pass_and_availability_are_scoped_to_partner(self):
        other = APIClient()
        response = other.post("/api/v1/partner/bookings/passes/", self.payload, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(other.get("/api/v1/partner/bookings/availability/").status_code, 401)
        self.assertEqual(self.create_pass(specialist_id=999999).status_code, 400)

    @override_settings(MOBILE_SMS_TEST_CODE="11111")
    def test_mobile_pass_api_creates_series_prices_each_date_and_retries_safely(self):
        mobile = APIClient()
        login = mobile.post("/api/v1/mobile/auth/verify-code/", {"phone": self.customer.phone, "code": "11111"}, format="json")
        self.assertEqual(login.status_code, 200)
        headers = {"HTTP_AUTHORIZATION": f"Bearer {login.data['tokens']['access_token']}"}
        payload = {
            **self.payload, "partner_id": self.partner.id,
            "starts_at": self.starts_at.isoformat(),
        }
        for changes in ({"visits": None}, {"visits": ["2099-02-30T10:00:00"]}, {"request_id": "bad"}):
            invalid = mobile.post("/api/v1/mobile/bookings/", {**payload, **changes}, format="json", **headers)
            self.assertEqual(invalid.status_code, 400, invalid.data)
            self.assertEqual(Booking.objects.count(), 0)
        outside = Booking.objects.create(tenant_slug="public", service_name="Outside visit", starts_at=self.visits[1], client_name="Outside client", client_phone=self.customer.phone)
        conflict = mobile.post("/api/v1/mobile/bookings/", payload, format="json", **headers)
        self.assertEqual(conflict.status_code, 409, conflict.data)
        self.assertEqual(BookingPass.objects.count(), 0)
        outside.delete()
        response = mobile.post("/api/v1/mobile/bookings/", payload, format="json", **headers)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["base_price"], "33.34")
        self.assertEqual(response.data["final_price"], "26.67")
        self.assertEqual(Booking.objects.get(visit_number=2).final_price, Decimal("33.33"))
        self.assertEqual(len(response.data["booking_pass"]["visits"]), 3)
        self.assertEqual(mobile.post("/api/v1/mobile/bookings/", payload, format="json", **headers).status_code, 200)
        self.assertEqual(Booking.objects.count(), 3)
        moved = self.client.patch(f"/api/v1/partner/bookings/{response.data['id']}/", {"starts_at": self.starts_at.replace(hour=12).isoformat()}, format="json", **self.headers)
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual(moved.data["base_price"], "33.34")
        self.assertEqual(moved.data["final_price"], "33.34")
