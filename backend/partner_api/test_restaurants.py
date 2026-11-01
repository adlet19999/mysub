from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from mobile_api.views import issue_tokens
from .models import Booking, BookingExtension, BusinessTable, Category
from .restaurant import renew_restaurant_bookings
from .test_lifecycle import LifecycleFixture


class RestaurantBookingTests(LifecycleFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.partner.business_category = "Кафе и рестораны"
        self.partner.save()
        self.category = Category.objects.get(tenant_slug="public", name="Кафе и рестораны")
        self.kind.category = self.category
        self.kind.save()
        self.individual.category = self.category
        self.individual.save()
        self.table = BusinessTable.objects.create(partner_profile=self.partner, tenant_slug="public", name="Table four", capacity=4)

    def reserve(self, **changes):
        return self.client.post("/api/v1/partner/bookings/", {
            "service_ids": [self.individual.id], "service_name": self.individual.name,
            "client_name": "Restaurant guest", "client_phone": self.customer.phone,
            "starts_at": self.starts_at.isoformat(), "party_size": 3, **changes,
        }, format="json", **self.headers)

    def action(self, booking_id, action, **values):
        return self.client.patch(f"/api/v1/partner/bookings/{booking_id}/restaurant/", {"action": action, **values}, format="json", **self.headers)

    def arrive(self, booking_id):
        with patch("partner_api.restaurant.timezone.now", return_value=self.starts_at + timedelta(minutes=5)):
            response = self.action(booking_id, "arrive")
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def test_automatically_assigns_smallest_suitable_table_and_two_hours(self):
        BusinessTable.objects.create(partner_profile=self.partner, tenant_slug="public", name="Table eight", capacity=8)
        response = self.reserve()
        self.assertEqual(response.status_code, 201, response.data)
        booking = Booking.objects.get(id=response.data["id"])
        self.assertEqual(booking.table_id, self.table.id)
        self.assertEqual(booking.ends_at - booking.starts_at, timedelta(hours=2))
        self.assertEqual(response.data["restaurant"]["party_size"], 3)
        self.assertEqual(response.data["restaurant"]["table_capacity"], 4)

    def test_full_interval_and_capacity_are_checked(self):
        self.assertEqual(self.reserve(party_size=5).status_code, 409)
        self.assertEqual(self.reserve().status_code, 201)
        self.assertEqual(self.reserve(starts_at=(self.starts_at + timedelta(minutes=90)).isoformat(), client_phone="+77000000010").status_code, 409)
        self.assertEqual(self.reserve(starts_at=(self.starts_at + timedelta(hours=2)).isoformat(), client_phone="+77000000010").status_code, 201)

    def test_second_table_accepts_simultaneous_different_clients(self):
        other = BusinessTable.objects.create(partner_profile=self.partner, tenant_slug="public", name="Table six", capacity=6)
        first = self.reserve()
        second = self.reserve(client_phone="+77000000010")
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(first.data["restaurant"]["table_id"], self.table.id)
        self.assertEqual(second.data["restaurant"]["table_id"], other.id)

    def test_invalid_party_sizes_never_create_bookings(self):
        for value in (0, -1, 1001, True, "3", 2.5, None):
            with self.subTest(value=value):
                self.assertEqual(self.reserve(party_size=value).status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_arrival_is_explicit_and_cannot_be_confirmed_before_start(self):
        created = self.reserve()
        self.assertEqual(self.action(created.data["id"], "arrive").status_code, 409)
        self.arrive(created.data["id"])
        self.assertEqual(Booking.objects.get(id=created.data["id"]).status, "arrived")

    def test_only_confirmed_arrivals_are_automatically_extended(self):
        created = self.reserve()
        now = self.starts_at + timedelta(hours=2, minutes=1)
        self.assertEqual(renew_restaurant_bookings(now), 0)
        self.arrive(created.data["id"])
        with patch("partner_api.restaurant.timezone.now", return_value=now):
            self.assertEqual(renew_restaurant_bookings(now), 1)
            self.assertEqual(renew_restaurant_bookings(now), 0)
        booking = Booking.objects.get(id=created.data["id"])
        self.assertEqual(booking.ends_at, self.starts_at + timedelta(hours=4))
        self.assertEqual(BookingExtension.objects.filter(booking=booking).count(), 1)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(booking.final_price, Decimal("10000.00"))

    def test_restart_catches_up_multiple_blocks_without_duplicate_orders(self):
        created = self.reserve()
        self.arrive(created.data["id"])
        now = self.starts_at + timedelta(hours=7)
        self.assertEqual(renew_restaurant_bookings(now), 1)
        self.assertEqual(BookingExtension.objects.count(), 3)
        self.assertEqual(Booking.objects.get(id=created.data["id"]).ends_at, self.starts_at + timedelta(hours=8))

    def test_future_booking_is_reassigned_when_teacher_equivalent_visit_overruns(self):
        first = self.reserve()
        second = self.reserve(starts_at=(self.starts_at + timedelta(hours=2)).isoformat(), client_phone="+77000000010")
        replacement = BusinessTable.objects.create(partner_profile=self.partner, tenant_slug="public", name="Replacement", capacity=4)
        self.arrive(first.data["id"])
        now = self.starts_at + timedelta(hours=2)
        with patch("partner_api.restaurant.timezone.now", return_value=now):
            self.assertEqual(renew_restaurant_bookings(now), 1)
        following = Booking.objects.get(id=second.data["id"])
        self.assertEqual(following.table_id, replacement.id)
        self.assertIn("автоматически", following.table_notice)
        self.assertEqual(following.starts_at, self.starts_at + timedelta(hours=2))

    def test_unresolved_overrun_conflict_is_visible_on_both_bookings(self):
        first = self.reserve()
        second = self.reserve(starts_at=(self.starts_at + timedelta(hours=2)).isoformat(), client_phone="+77000000010")
        self.arrive(first.data["id"])
        now = self.starts_at + timedelta(hours=2)
        with patch("partner_api.restaurant.timezone.now", return_value=now):
            with self.assertLogs("partner_api.restaurant", level="WARNING"):
                self.assertEqual(renew_restaurant_bookings(now), 1)
        for booking_id in (first.data["id"], second.data["id"]):
            self.assertIn("Конфликт", Booking.objects.get(id=booking_id).table_notice)

    def test_finish_requires_payment_and_confirmed_arrival(self):
        created = self.reserve()
        self.assertEqual(self.action(created.data["id"], "finish", paid_amount="5000").status_code, 409)
        self.arrive(created.data["id"])
        for amount in ("", "-1", "nan", "1.001", "10000000000"):
            self.assertEqual(self.action(created.data["id"], "finish", paid_amount=amount).status_code, 409)
        with patch("partner_api.restaurant.timezone.now", return_value=self.starts_at + timedelta(hours=1)):
            response = self.action(created.data["id"], "finish", paid_amount="5000.00")
        self.assertEqual(response.status_code, 200, response.data)
        booking = Booking.objects.get(id=created.data["id"])
        self.assertEqual(booking.status, "completed")
        self.assertEqual(booking.paid_amount, Decimal("5000.00"))
        self.assertEqual(booking.ends_at, self.starts_at + timedelta(hours=1))
        self.assertEqual(renew_restaurant_bookings(self.starts_at + timedelta(days=1)), 0)
        self.assertEqual(self.action(booking.id, "finish", paid_amount="5000").status_code, 200)
        self.assertEqual(self.action(booking.id, "finish", paid_amount="6000").status_code, 409)
        dashboard = self.client.get("/api/v1/common/admin/dashboard/", **self.admin_headers)
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        self.assertEqual(Decimal(dashboard.data["metrics"]["revenue_total"]), Decimal("5000"))

    def test_cancellation_and_no_show_release_table_but_keep_history(self):
        for action, status in (("cancel", "cancelled"), ("no_show", "no_show")):
            created = self.reserve()
            self.assertEqual(created.status_code, 201, created.data)
            self.assertEqual(self.action(created.data["id"], action).status_code, 200)
            self.assertEqual(Booking.objects.get(id=created.data["id"]).status, status)
        history = self.client.get("/api/v1/partner/bookings/", **self.headers)
        self.assertEqual(len(history.data), 2)
        self.assertEqual(self.reserve().status_code, 201)

    def test_active_guests_cannot_be_deleted_cancelled_or_archived(self):
        created = self.reserve()
        self.arrive(created.data["id"])
        self.assertEqual(self.action(created.data["id"], "cancel").status_code, 409)
        self.assertEqual(self.action(created.data["id"], "no_show").status_code, 409)
        self.assertEqual(self.client.delete(f"/api/v1/partner/bookings/{created.data['id']}/", **self.headers).status_code, 409)
        response = self.client.patch(f"/api/v1/partner/tables/{self.table.id}/", {"is_active": False}, format="json", **self.headers)
        self.assertEqual(response.status_code, 409)

    def test_pending_reservation_can_be_moved_without_affecting_other_visits(self):
        created = self.reserve()
        moved = self.starts_at + timedelta(days=1)
        response = self.action(created.data["id"], "move", starts_at=moved.isoformat(), party_size=4)
        self.assertEqual(response.status_code, 200, response.data)
        booking = Booking.objects.get(id=created.data["id"])
        self.assertEqual(booking.starts_at, moved)
        self.assertEqual(booking.ends_at, moved + timedelta(hours=2))
        self.assertEqual(BookingExtension.objects.count(), 0)

    def test_table_capacity_cannot_invalidate_existing_reservations(self):
        self.reserve()
        for changes in ({"capacity": 2}, {"is_active": False}):
            response = self.client.patch(f"/api/v1/partner/tables/{self.table.id}/", changes, format="json", **self.headers)
            self.assertEqual(response.status_code, 409)

    def test_mobile_client_reserves_without_selecting_table_or_specialist(self):
        tokens = issue_tokens(self.customer)
        response = self.client.post("/api/v1/mobile/bookings/", {
            "partner_id": self.partner.id, "service_id": self.individual.id,
            "starts_at": self.starts_at.isoformat(), "party_size": 3,
        }, format="json", HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["restaurant"]["table_id"], self.table.id)
        self.assertEqual(Booking.objects.get(id=response.data["id"]).booking_source, "mobile")

    def test_restaurant_slots_use_capacity_occupancy_and_offer_interval(self):
        self.individual.slot_interval_minutes = 15
        self.individual.save()
        endpoint = f"/api/v1/mobile/catalog/partners/{self.partner.id}/availability/"
        query = {"date": self.visit_date.isoformat(), "service_id": self.individual.id, "party_size": 3}
        response = self.client.get(endpoint, query)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["slot_interval_minutes"], 15)
        self.assertIn("10:15", response.data["slots"])
        self.reserve()
        blocked = self.client.get(endpoint, query)
        self.assertNotIn("10:15", blocked.data["slots"])
        self.assertIn("12:00", blocked.data["slots"])

    def test_restaurant_category_hides_groups_and_exposes_table_booking_mode(self):
        response = self.client.get("/api/v1/partner/booking-capabilities/", **self.headers)
        self.assertTrue(response.data["is_restaurant"])
        self.assertFalse(response.data["allows_group_services"])
        catalog = self.client.get(f"/api/v1/mobile/catalog/partners/{self.partner.id}/services/")
        service = next(item for item in catalog.data["data"] if item["id"] == self.individual.id)
        self.assertEqual(service["booking_mode"], "table")
        self.assertEqual(service["duration_minutes"], 120)

    def test_legacy_record_is_explicitly_assigned_without_changing_saved_cost(self):
        legacy = Booking.objects.create(tenant_slug="public", partner_profile=self.partner, service_name=self.individual.name, manager_name=self.specialist.full_name, starts_at=self.starts_at, client_name="Legacy guest", client_phone=self.customer.phone, base_price=Decimal("7500"), final_price=Decimal("7500"))
        response = self.action(legacy.id, "assign_table", service_id=self.individual.id, starts_at=self.starts_at.isoformat(), party_size=3)
        self.assertEqual(response.status_code, 200, response.data)
        legacy.refresh_from_db()
        self.assertEqual(legacy.table_id, self.table.id)
        self.assertEqual(legacy.final_price, Decimal("7500"))
        self.assertEqual(Booking.objects.count(), 1)

    def test_partner_table_create_checks_category_and_unique_name(self):
        response = self.client.post("/api/v1/partner/tables/", {"name": "Table two", "capacity": 2}, format="json", **self.headers)
        self.assertEqual(response.status_code, 201, response.data)
        duplicate = self.client.post("/api/v1/partner/tables/", {"name": "Table two", "capacity": 2}, format="json", **self.headers)
        self.assertEqual(duplicate.status_code, 409)
        invalid = self.client.post("/api/v1/partner/tables/", {"name": "Invalid", "capacity": 0}, format="json", **self.headers)
        self.assertEqual(invalid.status_code, 400)

    def test_capacity_and_bookings_are_scoped_to_partner(self):
        from django.contrib.auth.models import User
        from common_api.models import PartnerProfile
        other = PartnerProfile.objects.create(user=User.objects.create_user(username="other-restaurant"), phone="+77000000020", business_category="Кафе и рестораны")
        table = BusinessTable.objects.create(partner_profile=other, tenant_slug="public", name="Foreign table", capacity=8)
        self.assertEqual(self.reserve(party_size=8).status_code, 409)
        foreign = Booking.objects.create(partner_profile=other, tenant_slug="public", service_name="Foreign", manager_name=table.name, table=table, party_size=3, starts_at=self.starts_at, ends_at=self.starts_at + timedelta(hours=2), client_name="Foreign client", client_phone="+77000000021")
        self.assertEqual(self.action(foreign.id, "cancel").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/v1/partner/tables/{table.id}/", {"capacity": 9}, format="json", **self.headers).status_code, 404)

    def test_invalid_calendar_datetime_is_reported_not_an_internal_error(self):
        self.assertEqual(self.reserve(starts_at="2026-02-30T10:00:00+05:00").status_code, 400)

    def test_worker_management_command_runs_without_creating_duplicate_orders(self):
        from django.core.management import call_command
        from io import StringIO
        created = self.reserve()
        self.arrive(created.data["id"])
        with patch("partner_api.restaurant.timezone.now", return_value=self.starts_at + timedelta(hours=2)):
            output = StringIO()
            call_command("renew_restaurant_bookings", stdout=output)
            self.assertIn("1", output.getvalue())
            call_command("renew_restaurant_bookings", stdout=StringIO())
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(BookingExtension.objects.count(), 1)
