from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from common_api.models import PartnerProfile
from mobile_api.models import CustomerProfile, CustomerSubscription

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
		self.phone = "+77000000000"
		customer = CustomerProfile.objects.create(
			user=User.objects.create_user(username="pricing-customer"),
			phone=self.phone,
		)
		self.subscription = CustomerSubscription.objects.create(customer=customer)
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
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(15), client_phone=self.phone)
		self.assertEqual(pricing["base_price"], Decimal("1000.00"))
		self.assertEqual(pricing["discount_amount"], Decimal("200.00"))
		self.assertEqual(pricing["final_price"], Decimal("800.00"))
		self.assertEqual(pricing["pricing_details"][0]["discount_percent"], 20)

	def test_pricing_keeps_full_price_outside_promotion_windows(self):
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(12), client_phone=self.phone)
		self.assertEqual(pricing["discount_amount"], Decimal("0.00"))
		self.assertEqual(pricing["final_price"], Decimal("1000.00"))

	def test_booking_serializer_returns_price_snapshot(self):
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(10), client_phone=self.phone)
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

	def test_pricing_requires_subscription_for_each_customer(self):
		for phone in ("", "+77000000001"):
			with self.subTest(phone=phone):
				pricing = calculate_booking_pricing([self.service], self.specialist, self.at(15), client_phone=phone)
				self.assertEqual(pricing["final_price"], Decimal("1000.00"))
				self.assertEqual(pricing["pricing_details"][0]["discount_percent"], 0)

	def test_paused_expired_and_inactive_customers_pay_full_price(self):
		self.subscription.status = CustomerSubscription.Status.PAUSED
		self.subscription.save()
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(15), client_phone=self.phone)
		self.assertEqual(pricing["discount_amount"], Decimal("0.00"))
		self.subscription.status = CustomerSubscription.Status.ACTIVE
		self.subscription.expires_at = timezone.localdate() - timedelta(days=1)
		self.subscription.save()
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(15), client_phone=self.phone)
		self.assertEqual(pricing["discount_amount"], Decimal("0.00"))
		self.subscription.expires_at = None
		self.subscription.save()
		user = self.subscription.customer.user
		user.is_active = False
		user.save()
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(15), client_phone=self.phone)
		self.assertEqual(pricing["discount_amount"], Decimal("0.00"))

	def test_subscription_must_cover_visit_date_inclusively(self):
		visit_date = timezone.localdate() + timedelta(days=14)
		visit_date += timedelta(days=(-visit_date.weekday()) % 7)
		starts_at = timezone.make_aware(datetime.combine(visit_date, datetime.min.time()).replace(hour=15))
		for expires_at, expected in (
			(visit_date - timedelta(days=1), "1000.00"),
			(visit_date, "800.00"),
		):
			with self.subTest(expires_at=expires_at):
				self.subscription.expires_at = expires_at
				self.subscription.save()
				pricing = calculate_booking_pricing([self.service], self.specialist, starts_at, client_phone=self.phone)
				self.assertEqual(pricing["final_price"], Decimal(expected))

	def test_formatted_phone_matches_subscription(self):
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(15), client_phone="+7 (700) 000-00-00")
		self.assertEqual(pricing["final_price"], Decimal("800.00"))

	def test_entire_service_must_fit_discount_window(self):
		pricing = calculate_booking_pricing([self.service], self.specialist, self.at(10, 30), client_phone=self.phone)
		self.assertEqual(pricing["final_price"], Decimal("1000.00"))


class BookingPricingApiTests(TestCase):
	def setUp(self):
		self.booking_date = timezone.localdate() + timedelta(days=7)
		self.booking_date += timedelta(days=(-self.booking_date.weekday()) % 7)
		customer = CustomerProfile.objects.create(
			user=User.objects.create_user(username="api-pricing-customer"),
			phone="+77000000000",
		)
		CustomerSubscription.objects.create(customer=customer)
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

	def at(self, hour, minute=0):
		return timezone.make_aware(datetime.combine(self.booking_date, datetime.min.time()).replace(hour=hour, minute=minute))

	def test_booking_price_snapshot_is_created_and_recalculated_on_move(self):
		created = self.client.post(
			"/api/v1/partner/bookings/",
			{
				"service_name": self.service.name,
				"service_ids": [self.service.id],
				"manager_name": self.specialist.full_name,
				"starts_at": self.at(15).isoformat(),
				"client_name": "Клиент",
				"client_phone": "+77000000000",
			},
			format="json",
			**self.headers,
		)
		self.assertEqual(created.status_code, 201)
		self.assertEqual(created.data["base_price"], "1000.00")
		self.assertEqual(created.data["discount_amount"], "0.00")
		self.assertEqual(created.data["final_price"], "1000.00")

		updated = self.client.patch(
			f"/api/v1/partner/bookings/{created.data['id']}/",
			{
				"starts_at": self.at(12).isoformat(),
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

	def test_changing_customer_keeps_manual_booking_at_full_price(self):
		created = self.client.post(
			"/api/v1/partner/bookings/",
			{
				"service_name": self.service.name,
				"service_ids": [self.service.id],
				"manager_name": self.specialist.full_name,
				"starts_at": self.at(15).isoformat(),
				"client_name": "Клиент",
				"client_phone": "+7 (700) 000-00-00",
			}, format="json", **self.headers,
		)
		self.assertEqual(created.status_code, 201)
		self.assertEqual(created.data["final_price"], "1000.00")
		updated = self.client.patch(
			f"/api/v1/partner/bookings/{created.data['id']}/",
			{"client_phone": "+77000000001"}, format="json", **self.headers,
		)
		self.assertEqual(updated.status_code, 200)
		self.assertEqual(updated.data["final_price"], "1000.00")
		self.assertFalse(updated.data["subscription_active"])

	def test_manual_group_subscribers_and_nonsubscribers_pay_full_price(self):
		from common_api.models import BusinessCategory

		BusinessCategory.objects.create(name="Салон", allows_group_services=True)
		self.service.service_type = "group"
		self.service.details = {"min_people": 1, "max_people": 3}
		self.service.save()
		for phone, expected in (("+77000000000", "1000.00"), ("+77000000001", "1000.00")):
			created = self.client.post(
				"/api/v1/partner/bookings/",
				{
					"service_name": self.service.name,
					"service_ids": [self.service.id],
					"manager_name": self.specialist.full_name,
					"starts_at": self.at(15).isoformat(),
					"client_name": "Клиент",
					"client_phone": phone,
				}, format="json", **self.headers,
			)
			self.assertEqual(created.status_code, 201)
			self.assertEqual(created.data["final_price"], expected)
		participants = created.data["group_session"]["participants"]
		self.assertEqual([(p["final_price"], p["subscription_active"]) for p in participants], [("1000.00", True), ("1000.00", False)])

	def test_status_change_preserves_price_snapshot(self):
		created = self.client.post(
			"/api/v1/partner/bookings/",
			{
				"service_name": self.service.name,
				"service_ids": [self.service.id],
				"manager_name": self.specialist.full_name,
				"starts_at": self.at(15).isoformat(),
				"client_name": "Клиент",
				"client_phone": "+77000000000",
			}, format="json", **self.headers,
		)
		self.assertEqual(created.status_code, 201)
		CustomerSubscription.objects.all().delete()
		updated = self.client.patch(
			f"/api/v1/partner/bookings/{created.data['id']}/",
			{"status": "completed"}, format="json", **self.headers,
		)
		self.assertEqual(updated.status_code, 200)
		self.assertEqual(updated.data["final_price"], "1000.00")

	def test_group_format_requires_category_permission_and_capacity(self):
		from common_api.models import BusinessCategory

		category = BusinessCategory.objects.create(name="Салон", allows_group_services=False)
		url = f"/api/v1/partner/services/{self.service.id}/"
		response = self.client.patch(url, {"service_type": "group", "details": {"min_people": 1, "max_people": 3}}, format="json", **self.headers)
		self.assertEqual(response.status_code, 400)
		category.allows_group_services = True
		category.save()
		response = self.client.patch(url, {"service_type": "group"}, format="json", **self.headers)
		self.assertEqual(response.status_code, 400)
		response = self.client.patch(url, {"service_type": "group", "details": {"min_people": 1, "max_people": 3}}, format="json", **self.headers)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["details"]["max_people"], 3)

	def test_group_slot_capacity_and_cancelled_place(self):
		from common_api.models import BusinessCategory

		BusinessCategory.objects.create(name="Салон", allows_group_services=True)
		self.service.service_type = "group"
		self.service.details = {"min_people": 1, "max_people": 2}
		self.service.save()
		payload = {"service_name": self.service.name, "service_ids": [self.service.id], "manager_name": self.specialist.full_name, "starts_at": self.at(15).isoformat(), "client_name": "Клиент"}
		first = self.client.post("/api/v1/partner/bookings/", {**payload, "client_phone": "+77000000001"}, format="json", **self.headers)
		second = self.client.post("/api/v1/partner/bookings/", {**payload, "client_phone": "+77000000002"}, format="json", **self.headers)
		self.assertEqual(first.status_code, 201)
		self.assertEqual(second.status_code, 201)
		duplicate = self.client.post("/api/v1/partner/bookings/", {**payload, "client_phone": "+77000000002"}, format="json", **self.headers)
		self.assertEqual(duplicate.status_code, 409)
		third = self.client.post("/api/v1/partner/bookings/", {**payload, "client_phone": "+77000000003"}, format="json", **self.headers)
		self.assertEqual(third.status_code, 409)
		Booking.objects.filter(id=first.data["id"]).update(status="cancelled")
		third = self.client.post("/api/v1/partner/bookings/", {**payload, "client_phone": "+77000000003"}, format="json", **self.headers)
		self.assertEqual(third.status_code, 201)
		overlap = self.client.post("/api/v1/partner/bookings/", {**payload, "client_phone": "+77000000004", "starts_at": self.at(15, 30).isoformat()}, format="json", **self.headers)
		self.assertEqual(overlap.status_code, 409)
		movable = self.client.post(
			"/api/v1/partner/bookings/",
			{**payload, "client_phone": "+77000000005", "starts_at": self.at(16).isoformat()},
			format="json",
			**self.headers,
		)
		self.assertEqual(movable.status_code, 201)
		move_to_full_group = self.client.patch(
			f"/api/v1/partner/bookings/{movable.data['id']}/",
			{"starts_at": self.at(15).isoformat()},
			format="json",
			**self.headers,
		)
		self.assertEqual(move_to_full_group.status_code, 409)
		movable_booking = Booking.objects.get(id=movable.data["id"])
		self.assertEqual(movable_booking.starts_at, self.at(16))

	def test_group_completion_updates_each_participant(self):
		from common_api.models import BusinessCategory

		BusinessCategory.objects.create(name="Салон", allows_group_services=True)
		self.service.service_type = "group"
		self.service.details = {"min_people": 1, "max_people": 3}
		self.service.save()
		pricing = calculate_booking_pricing([self.service], self.specialist, timezone.make_aware(datetime(2026, 4, 20, 15)))
		members = [Booking.objects.create(tenant_slug="public", partner_profile=self.partner_profile, service_name=self.service.name, manager_name=self.specialist.full_name, starts_at=timezone.make_aware(datetime(2026, 4, 20, 15)), client_name=f"Клиент {index}", client_phone=f"+7700000000{index}", **pricing) for index in range(3)]
		payload = serialize_booking(members[0])
		self.assertEqual(payload["group_session"]["capacity"], 3)
		self.assertEqual(len(payload["group_session"]["participants"]), 3)
		self.assertTrue(payload["group_session"]["participants"][0]["subscription_active"])
		self.assertFalse(payload["group_session"]["participants"][1]["subscription_active"])
		foreign = self.client.patch(f"/api/v1/partner/bookings/{members[0].id}/", {"group_action": "complete", "participant_ids": [999999]}, format="json", **self.headers)
		self.assertEqual(foreign.status_code, 409)
		response = self.client.patch(f"/api/v1/partner/bookings/{members[0].id}/", {"group_action": "complete", "participant_ids": [members[0].id, members[1].id]}, format="json", **self.headers)
		self.assertEqual(response.status_code, 200)
		for index, member in enumerate(members):
			member.refresh_from_db()
			self.assertEqual(member.status, "completed" if index < 2 else "no_show")

	def test_service_capacity_and_format_changes_preserve_upcoming_bookings(self):
		from common_api.models import BusinessCategory

		BusinessCategory.objects.create(name="Салон", allows_group_services=True)
		self.service.service_type = "group"
		self.service.details = {"min_people": 1, "max_people": 3}
		self.service.save()
		starts_at = timezone.now() + timedelta(days=2)
		pricing = calculate_booking_pricing([self.service], self.specialist, starts_at)
		for index in range(2):
			Booking.objects.create(tenant_slug="public", partner_profile=self.partner_profile, service_name=self.service.name, manager_name=self.specialist.full_name, starts_at=starts_at, client_name="Клиент", client_phone=f"+7700000000{index}", **pricing)
		url = f"/api/v1/partner/services/{self.service.id}/"
		for changes in ({"details": {"min_people": 1, "max_people": 1}}, {"service_type": "individual"}, {"duration_minutes": 30}):
			response = self.client.patch(url, changes, format="json", **self.headers)
			self.assertEqual(response.status_code, 409)
		response = self.client.patch(url, {"details": {"min_people": 1, "max_people": 4}}, format="json", **self.headers)
		self.assertEqual(response.status_code, 200)


class SpecialistArchivingApiTests(TestCase):
	def setUp(self):
		user = User.objects.create_user(
			username="partner@example.com",
			email="partner@example.com",
		)
		self.partner_profile = PartnerProfile.objects.create(
			user=user,
			phone="+77000000000",
			user_type="partner",
		)
		self.specialist = Specialist.objects.create(
			tenant_slug="public",
			partner_profile=self.partner_profile,
			full_name="Аружан",
			phone="+77000000001",
		)
		self.client = APIClient()
		self.headers = {
			"HTTP_X_TENANT": "public",
			"HTTP_X_PARTNER_EMAIL": "partner@example.com",
		}

	def create_booking(self, status="booked"):
		return Booking.objects.create(
			tenant_slug="public",
			partner_profile=self.partner_profile,
			service_name="Стрижка",
			manager_name=self.specialist.full_name,
			starts_at=timezone.make_aware(datetime(2026, 4, 20, 10)),
			client_name="Клиент",
			client_phone="+77000000000",
			status=status,
		)

	def test_specialist_with_active_booking_may_not_be_archived(self):
		self.create_booking()

		response = self.client.patch(
			f"/api/v1/partner/specialists/{self.specialist.id}/",
			{"is_active": False},
			format="json",
			**self.headers,
		)

		self.assertEqual(response.status_code, 409)
		self.assertEqual(
			response.data["message"],
			"Нельзя архивировать специалиста: у него есть незавершенные записи",
		)
		self.specialist.refresh_from_db()
		self.assertTrue(self.specialist.is_active)

	def test_specialist_with_completed_booking_may_be_archived(self):
		self.create_booking(status="completed")

		response = self.client.patch(
			f"/api/v1/partner/specialists/{self.specialist.id}/",
			{"is_active": False},
			format="json",
			**self.headers,
		)

		self.assertEqual(response.status_code, 200)
		self.specialist.refresh_from_db()
		self.assertFalse(self.specialist.is_active)

	def test_day_with_completed_booking_may_not_be_made_day_off(self):
		schedule = weekday_working_schedule()
		self.specialist.working_schedule = schedule
		self.specialist.save(update_fields=["working_schedule"])
		self.create_booking(status="completed")
		monday = next(day for day in schedule if day["day"] == "mon")
		monday.update({"is_day_off": True})

		response = self.client.patch(
			f"/api/v1/partner/specialists/{self.specialist.id}/",
			{"working_schedule": schedule},
			format="json",
			**self.headers,
		)

		self.assertEqual(response.status_code, 409)
		self.assertIn("на этот день есть записи", response.data["message"])

	def test_break_may_not_overlap_completed_booking(self):
		schedule = weekday_working_schedule()
		self.specialist.working_schedule = schedule
		self.specialist.save(update_fields=["working_schedule"])
		self.create_booking(status="completed")
		monday = next(day for day in schedule if day["day"] == "mon")
		monday["breaks"] = [{"name": "Перерыв", "start_time": "10:00", "end_time": "11:00"}]

		response = self.client.patch(
			f"/api/v1/partner/specialists/{self.specialist.id}/",
			{"working_schedule": schedule},
			format="json",
			**self.headers,
		)

		self.assertEqual(response.status_code, 409)
		self.assertIn("перерыв", response.data["message"].lower())
