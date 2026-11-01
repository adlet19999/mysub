from datetime import timedelta

from django.test import TestCase

from mobile_api.views import issue_tokens
from .models import Booking
from .test_lifecycle import LifecycleFixture


class BookingIntervalTests(LifecycleFixture, TestCase):
    def test_hour_service_with_half_hour_starts_still_checks_whole_duration(self):
        self.individual.slot_interval_minutes = 30
        self.individual.save()
        query = {"date": self.visit_date.isoformat(), "service_ids": str(self.individual.id), "specialist_id": str(self.specialist.id)}
        response = self.client.get("/api/v1/partner/bookings/availability/", query, **self.headers)
        self.assertIn("10:30", response.data["slots"])
        self.assertNotIn("10:15", response.data["slots"])
        self.assertEqual(self.book(service=self.individual).status_code, 201)
        blocked = self.client.get("/api/v1/partner/bookings/availability/", query, **self.headers)
        self.assertNotIn("10:30", blocked.data["slots"])
        self.assertIn("11:00", blocked.data["slots"])

    def test_fifteen_minute_medical_service_has_quarter_hour_mobile_starts(self):
        self.individual.slot_interval_minutes = 15
        self.individual.duration_minutes = 15
        self.individual.save()
        availability = self.client.get(f"/api/v1/mobile/catalog/partners/{self.partner.id}/specialists/{self.specialist.id}/availability/", {"date": self.visit_date.isoformat(), "service_id": self.individual.id})
        self.assertEqual(availability.data["slot_interval_minutes"], 15)
        self.assertIn("10:15", availability.data["slots"])
        tokens = issue_tokens(self.customer)
        response = self.client.post("/api/v1/mobile/bookings/", {"partner_id": self.partner.id, "specialist_id": self.specialist.id, "service_id": self.individual.id, "starts_at": (self.starts_at + timedelta(minutes=15)).isoformat()}, format="json", HTTP_AUTHORIZATION=f"Bearer {tokens['access_token']}")
        self.assertEqual(response.status_code, 201, response.data)

    def test_direct_create_and_move_cannot_bypass_configured_interval(self):
        self.individual.slot_interval_minutes = 30
        self.individual.save()
        invalid = self.starts_at + timedelta(minutes=15)
        self.assertEqual(self.book(service=self.individual, starts_at=invalid).status_code, 400)
        response = self.book(service=self.individual)
        moved = self.client.patch(f"/api/v1/partner/bookings/{response.data['id']}/", {"starts_at": invalid.isoformat()}, format="json", **self.headers)
        self.assertEqual(moved.status_code, 400)
        self.assertEqual(Booking.objects.get(id=response.data["id"]).starts_at, self.starts_at)

    def test_interval_is_validated_and_persisted_in_all_service_responses(self):
        for value in (0, 7, 121, True, "15"):
            response = self.client.patch(f"/api/v1/partner/services/{self.individual.id}/", {"slot_interval_minutes": value}, format="json", **self.headers)
            self.assertEqual(response.status_code, 400, response.data)
        response = self.client.patch(f"/api/v1/partner/services/{self.individual.id}/", {"slot_interval_minutes": 15}, format="json", **self.headers)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["slot_interval_minutes"], 15)
        listing = self.client.get("/api/v1/partner/services/", **self.headers)
        service = next(item for item in listing.data if item["id"] == self.individual.id)
        self.assertEqual(service["slot_interval_minutes"], 15)

    def test_beauty_category_disallows_groups_but_keeps_individual_passes(self):
        self.partner.business_category = "Салоны красоты"
        self.partner.save()
        self.individual.is_pass = True
        self.individual.visit_count = 5
        self.individual.save()
        response = self.client.get("/api/v1/partner/booking-capabilities/", **self.headers)
        self.assertFalse(response.data["allows_group_services"])
        self.assertTrue(response.data["has_individual_passes"])
        self.assertFalse(response.data["is_restaurant"])
        self.assertEqual(self.client.get("/api/v1/partner/tables/", **self.headers).status_code, 403)

    def test_cancelled_ordinary_booking_stays_in_client_and_booking_history(self):
        created = self.book(service=self.individual)
        self.assertEqual(created.status_code, 201)
        response = self.client.delete(f"/api/v1/partner/bookings/{created.data['id']}/", **self.headers)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Booking.objects.get(id=created.data["id"]).status, "cancelled")
        history = self.client.get("/api/v1/partner/bookings/", **self.headers)
        self.assertEqual(len(history.data), 1)
