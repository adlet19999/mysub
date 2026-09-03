from datetime import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common_api.models import PartnerProfile

from .models import Booking, Category, Service, ServiceKind, Specialist, SpecialistService
from .views import (
	booking_schedule_error,
	calculate_booking_pricing,
	default_working_schedule,
	has_client_booking_overlap,
	normalize_working_schedule,
	serialize_booking,
)


def weekday_working_schedule():
	schedule = default_working_schedule()
	for day in schedule:
		if day["day"] in {"sat", "sun"}:
			continue
		day.update(
			{
				"is_day_off": False,
				"start_time": "09:00",
				"end_time": "18:00",
				"discount_start": "10:00",
				"discount_end": "16:00",
				"breaks": [{"name": "Обед", "start_time": "13:00", "end_time": "14:00"}],
			}
		)
	return schedule


class BookingScheduleValidationTests(TestCase):
	def setUp(self):
		self.specialist = Specialist.objects.create(
			tenant_slug="public",
			full_name="Аружан",
			phone="+77000000000",
			working_schedule=weekday_working_schedule(),
		)

	def at(self, hour, minute=0):
		return timezone.make_aware(datetime(2026, 4, 20, hour, minute))

	def test_booking_may_not_overlap_break(self):
		self.assertEqual(booking_schedule_error(self.specialist, self.at(12, 30), 60), "Запись пересекается с перерывом: Обед")

	def test_booking_may_not_be_created_on_day_off(self):
		starts_at = timezone.make_aware(datetime(2026, 4, 19, 10, 0))
		self.assertEqual(booking_schedule_error(self.specialist, starts_at, 60), "У специалиста выходной в выбранный день")

	def test_booking_inside_working_hours_is_allowed(self):
		self.assertIsNone(booking_schedule_error(self.specialist, self.at(14), 60))

	def test_default_schedule_marks_every_day_as_day_off(self):
		self.assertTrue(all(day["is_day_off"] for day in default_working_schedule()))
		self.assertTrue(all(day["discount_windows"] == [] for day in default_working_schedule()))

	def test_legacy_discount_times_are_normalized_to_one_window(self):
		schedule = weekday_working_schedule()
		for day in schedule:
			day.pop("discount_windows", None)
		normalized, error = normalize_working_schedule(schedule)
		self.assertIsNone(error)
		monday = next(day for day in normalized if day["day"] == "mon")
		self.assertEqual(monday["discount_windows"], [{"start_time": "10:00", "end_time": "16:00"}])

	def test_empty_discount_windows_disable_promotion(self):
		schedule = weekday_working_schedule()
		for day in schedule:
			day["discount_windows"] = []
			normalized, error = normalize_working_schedule(schedule)
		self.assertIsNone(error)
		monday = next(day for day in normalized if day["day"] == "mon")
		self.assertEqual(monday["discount_windows"], [])
		self.assertEqual(monday["discount_start"], "")
		self.assertEqual(monday["discount_end"], "")

	def test_overlapping_discount_windows_are_rejected(self):
		schedule = weekday_working_schedule()
		for day in schedule:
			day["discount_windows"] = [
				{"start_time": "10:00", "end_time": "13:00"},
				{"start_time": "12:00", "end_time": "16:00"},
			]
		normalized, error = normalize_working_schedule(schedule)
		self.assertIsNone(normalized)
		self.assertEqual(error, "Время скидок для mon не должно пересекаться")

	def test_date_override_does_not_change_other_same_weekdays(self):
		schedule, error = normalize_working_schedule(weekday_working_schedule() + [{
			"day": "sat", "date": "2026-08-01", "is_day_off": False,
			"start_time": "09:00", "end_time": "18:00", "discount_start": "10:00", "discount_end": "16:00",
			"breaks": [],
		}])
		self.assertIsNone(error)
		self.specialist.working_schedule = schedule
		self.assertIsNone(booking_schedule_error(self.specialist, timezone.make_aware(datetime(2026, 8, 1, 10)), 60))
		self.assertEqual(booking_schedule_error(self.specialist, timezone.make_aware(datetime(2026, 8, 8, 10)), 60), "У специалиста выходной в выбранный день")

	def test_client_may_not_have_overlapping_active_bookings(self):
		Booking.objects.create(
			tenant_slug="public",
			service_name="Стрижка",
			starts_at=self.at(10),
			client_name="Клиент",
			client_phone="+7 (700) 000-00-00",
		)
		self.assertTrue(has_client_booking_overlap("public", "+77000000000", self.at(10, 30), 60))

	def test_client_may_book_after_previous_service_finishes(self):
		Booking.objects.create(
			tenant_slug="public",
			service_name="Стрижка",
			starts_at=self.at(10),
			client_name="Клиент",
			client_phone="+77000000000",
		)
		self.assertFalse(has_client_booking_overlap("public", "+77000000000", self.at(11), 60))


class BookingPricingTests(TestCase):
	def setUp(self):
		category = Category.objects.create(tenant_slug="public", name="Салон")
		kind = ServiceKind.objects.create(tenant_slug="public", category=category, name="Стрижки")
		schedule = default_working_schedule()
		monday = next(day for day in schedule if day["day"] == "mon")
		monday.update(
			{
				"is_day_off": False,
				"start_time": "09:00",
				"end_time": "18:00",
				"discount_windows": [
					{"start_time": "10:00", "end_time": "11:00"},
					{"start_time": "15:00", "end_time": "17:00"},
				],
				"breaks": [],
			}
		)
		self.specialist = Specialist.objects.create(
			tenant_slug="public",
			full_name="Аружан",
			phone="+77000000000",
			working_schedule=schedule,
		)
		self.service = Service.objects.create(
			tenant_slug="public",
			category=category,
			kind=kind,
			name="Стрижка",
			duration_minutes=60,
			price=Decimal("1000.00"),
			discount_percent=20,
		)

	def at(self, hour, minute=0):
		return timezone.make_aware(datetime(2026, 4, 20, hour, minute))

	def test_pricing_applies_discount_inside_any_promotion_window(self):
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(15))
		self.assertEqual(pricing["base_price"], Decimal("1000.00"))
		self.assertEqual(pricing["discount_amount"], Decimal("200.00"))
		self.assertEqual(pricing["final_price"], Decimal("800.00"))
		self.assertEqual(pricing["pricing_details"][0]["discount_percent"], 20)

	def test_pricing_keeps_full_price_outside_promotion_windows(self):
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(12))
		self.assertEqual(pricing["discount_amount"], Decimal("0.00"))
		self.assertEqual(pricing["final_price"], Decimal("1000.00"))

	def test_booking_serializer_returns_price_snapshot(self):
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(10))
		booking = Booking.objects.create(
			tenant_slug="public",
			service_name=self.service.name,
			manager_name=self.specialist.full_name,
			starts_at=self.at(10),
			client_name="Клиент",
			client_phone="+77000000000",
			**pricing,
		)
		payload = serialize_booking(booking)
		self.assertEqual(payload["base_price"], "1000.00")
		self.assertEqual(payload["discount_amount"], "200.00")
		self.assertEqual(payload["final_price"], "800.00")


class BookingPricingApiTests(TestCase):
	def setUp(self):
		user = User.objects.create_user(username="partner@example.com", email="partner@example.com")
		self.partner_profile = PartnerProfile.objects.create(user=user, phone="+77000000000", user_type="partner")
		category = Category.objects.create(tenant_slug="public", name="Салон")
		kind = ServiceKind.objects.create(tenant_slug="public", category=category, name="Стрижки")
		schedule = default_working_schedule()
		monday = next(day for day in schedule if day["day"] == "mon")
		monday.update(
			{
				"is_day_off": False,
				"start_time": "09:00",
				"end_time": "18:00",
				"discount_windows": [
					{"start_time": "10:00", "end_time": "11:00"},
					{"start_time": "15:00", "end_time": "17:00"},
				],
				"breaks": [],
			}
		)
		self.specialist = Specialist.objects.create(
			tenant_slug="public",
			partner_profile=self.partner_profile,
			full_name="Аружан",
			phone="+77000000000",
			working_schedule=schedule,
		)
		self.service = Service.objects.create(
			tenant_slug="public",
			partner_profile=self.partner_profile,
			category=category,
			kind=kind,
			name="Стрижка",
			duration_minutes=60,
			price=Decimal("1000.00"),
			discount_percent=20,
		)
		SpecialistService.objects.create(specialist=self.specialist, service=self.service)
		self.client = APIClient()
		self.headers = {
			"HTTP_X_TENANT": "public",
			"HTTP_X_PARTNER_EMAIL": "partner@example.com",
		}

	def test_booking_price_snapshot_is_created_and_recalculated_on_move(self):
		created = self.client.post(
			"/api/v1/partner/bookings/",
			{
				"service_name": self.service.name,
				"service_ids": [self.service.id],
				"manager_name": self.specialist.full_name,
				"starts_at": "2026-04-20T15:00:00Z",
				"client_name": "Клиент",
				"client_phone": "+77000000000",
			},
			format="json",
			**self.headers,
		)
		self.assertEqual(created.status_code, 201)
		self.assertEqual(created.data["base_price"], "1000.00")
		self.assertEqual(created.data["discount_amount"], "200.00")
		self.assertEqual(created.data["final_price"], "800.00")

		updated = self.client.patch(
			f"/api/v1/partner/bookings/{created.data['id']}/",
			{
				"starts_at": "2026-04-20T12:00:00Z",
				"service_ids": [self.service.id],
			},
			format="json",
			**self.headers,
		)
		self.assertEqual(updated.status_code, 200)
		self.assertEqual(updated.data["base_price"], "1000.00")
		self.assertEqual(updated.data["discount_amount"], "0.00")
		self.assertEqual(updated.data["final_price"], "1000.00")
		booking = Booking.objects.get(id=created.data["id"])
		self.assertEqual(booking.final_price, Decimal("1000.00"))
