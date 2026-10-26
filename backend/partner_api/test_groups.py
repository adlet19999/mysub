import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from .group_views import GroupEnrollView
from .models import Booking, BookingGroup, BookingPass, GroupSession
from .test_lifecycle import LifecycleFixture


class IndependentGroupTests(LifecycleFixture, TestCase):
	def setUp(self):
		super().setUp()
		self.service.is_pass = True
		self.service.visit_count = 3
		self.service.pass_price_mode = "total"
		self.service.price = Decimal("100.00")
		self.service.save()
		self.dates = [self.starts_at + timedelta(weeks=index) for index in range(3)]
		self.payload = {
			"request_id": str(uuid.uuid4()), "name": "Morning group", "capacity": 2,
			"service_id": self.service.id, "specialist_id": self.specialist.id,
			"sessions": [value.isoformat() for value in self.dates],
		}

	def create_group(self, **changes):
		return self.client.post("/api/v1/partner/groups/", {**self.payload, **changes}, format="json", **self.headers)

	def enroll(self, group, phone="+77009990003", **changes):
		return self.client.post(f"/api/v1/partner/groups/{group['id']}/enroll/", {
			"request_id": str(uuid.uuid4()), "client_name": "Group client",
			"client_phone": phone, "session_ids": [item["id"] for item in group["sessions"]], **changes,
		}, format="json", **self.headers)

	def act(self, booking_id, **changes):
		return self.client.patch(f"/api/v1/partner/groups/participants/{booking_id}/", changes, format="json", **self.headers)

	def test_empty_group_exists_and_reserves_all_specialist_time(self):
		response = self.create_group()
		self.assertEqual(response.status_code, 201, response.data)
		self.assertEqual(Booking.objects.count(), 0)
		self.assertEqual(BookingPass.objects.count(), 0)
		self.assertEqual(len(response.data["sessions"]), 3)
		self.assertEqual([item["occupied_places"] for item in response.data["sessions"]], [0, 0, 0])
		self.assertEqual([item["base_price"] for item in response.data["sessions"]], ["33.34", "33.33", "33.33"])
		conflict = self.book(service=self.individual, starts_at=self.starts_at - timedelta(minutes=30))
		self.assertEqual(conflict.status_code, 409)
		availability = self.client.get("/api/v1/partner/bookings/availability/", {
			"date": self.visit_date.isoformat(), "specialist_id": self.specialist.id,
			"service_ids": str(self.individual.id),
		}, **self.headers)
		self.assertNotIn("09:30", availability.data["slots"])
		self.assertNotIn("10:00", availability.data["slots"])
		self.assertIn("10:00", self.slots())
		reserve = self.client.get("/api/v1/partner/bookings/availability/", {
			"date": self.visit_date.isoformat(), "specialist_id": self.specialist.id,
			"service_ids": str(self.service.id), "reserve_group": "1",
		}, **self.headers)
		self.assertNotIn("10:00", reserve.data["slots"])
		self.assertEqual(len(self.client.get("/api/v1/partner/groups/sessions/", **self.headers).data["items"]), 3)

	def test_create_retries_are_idempotent_and_conflicts_are_atomic(self):
		first = self.create_group()
		self.assertEqual(self.create_group().data["id"], first.data["id"])
		self.assertEqual(self.create_group(name="Changed").status_code, 409)
		self.assertEqual(BookingGroup.objects.count(), 1)
		self.assertEqual(self.create_group(request_id=str(uuid.uuid4())).status_code, 409)
		self.assertEqual(GroupSession.objects.count(), 3)

	def test_last_date_conflict_does_not_create_partial_group(self):
		self.assertEqual(self.book(service=self.individual, starts_at=self.dates[-1]).status_code, 201)
		self.assertEqual(self.create_group().status_code, 409)
		self.assertFalse(BookingGroup.objects.exists())

	def test_invalid_dates_count_capacity_and_specialist_are_rejected(self):
		for changes in (
			{"capacity": 0}, {"capacity": 3}, {"sessions": []}, {"sessions": ["bad"]},
			{"sessions": ["2099-02-30T10:00:00"]}, {"specialist_id": 99999},
			{"sessions": [self.dates[0].isoformat()] * 3}, {"sessions": self.payload["sessions"][:2]},
		):
			with self.subTest(changes=changes):
				self.assertIn(self.create_group(**changes).status_code, {400, 409})
				self.assertFalse(BookingGroup.objects.exists())

	def test_enrollment_uses_selected_dates_and_snapshot_prices(self):
		group = self.create_group().data
		self.service.price = Decimal("999.00")
		self.service.duration_minutes = 120
		self.service.save()
		response = self.enroll(group, session_ids=[group["sessions"][1]["id"], group["sessions"][2]["id"]])
		self.assertEqual(response.status_code, 201, response.data)
		bookings = list(Booking.objects.order_by("visit_number"))
		self.assertEqual([item.base_price for item in bookings], [Decimal("33.33"), Decimal("33.33")])
		self.assertEqual(bookings[0].booking_pass.total_price, Decimal("66.66"))
		self.assertEqual(bookings[0].pricing_details[0]["duration_minutes"], 60)
		self.assertEqual([item["occupied_places"] for item in response.data["sessions"]], [0, 1, 1])

	def test_capacity_is_per_session_and_no_partial_enrollment_is_written(self):
		group = self.create_group().data
		self.assertEqual(self.enroll(group).status_code, 201)
		self.assertEqual(self.enroll(group, phone="+77009990004", session_ids=[group["sessions"][-1]["id"]]).status_code, 201)
		self.assertEqual(self.enroll(group, phone="+77009990005").status_code, 409)
		self.assertEqual(Booking.objects.count(), 4)
		self.assertEqual(BookingPass.objects.count(), 2)

	def test_enrollment_retry_and_client_conflicts(self):
		group = self.create_group().data
		key = str(uuid.uuid4())
		self.assertEqual(self.enroll(group, request_id=key).status_code, 201)
		self.assertEqual(self.enroll(group, request_id=key).status_code, 200)
		self.assertEqual(self.enroll(group, phone="+77009990004", request_id=key).status_code, 409)
		self.assertEqual(self.enroll(group).status_code, 409)
		self.assertEqual(Booking.objects.count(), 3)

	def test_cancellation_only_affects_one_client_visit_and_keeps_empty_session(self):
		group = self.create_group().data
		self.enroll(group)
		self.enroll(group, phone="+77009990004")
		bookings = list(Booking.objects.order_by("id"))
		self.assertEqual(self.act(bookings[0].id, action="cancel").status_code, 200)
		for booking in bookings[1:]:
			booking.refresh_from_db()
			self.assertEqual(booking.status, "booked")
		self.assertEqual(self.act(bookings[3].id, action="cancel").status_code, 200)
		session = GroupSession.objects.get(id=group["sessions"][0]["id"])
		self.assertEqual(session.bookings.exclude(status="cancelled").count(), 0)
		self.assertEqual(GroupSession.objects.count(), 3)
		self.assertEqual(self.book(service=self.individual).status_code, 409)

	def test_attendance_does_not_mark_any_other_client_absent(self):
		group = self.create_group().data
		self.enroll(group)
		self.enroll(group, phone="+77009990004")
		first, other = list(Booking.objects.filter(group_session_id=group["sessions"][0]["id"]).order_by("id"))
		self.assertEqual(self.act(first.id, action="complete").status_code, 200)
		other.refresh_from_db()
		self.assertEqual(other.status, "booked")
		self.assertEqual(self.act(first.id, action="move", session_id=group["sessions"][1]["id"]).status_code, 409)

	def test_move_to_another_group_preserves_price_and_other_visits(self):
		group = self.create_group().data
		other = self.create_group(request_id=str(uuid.uuid4()), name="Later group", sessions=[(value + timedelta(hours=1)).isoformat() for value in self.dates]).data
		self.enroll(group)
		self.enroll(group, phone="+77009990004")
		bookings = list(Booking.objects.order_by("id"))
		response = self.act(bookings[0].id, action="move", session_id=other["sessions"][0]["id"])
		self.assertEqual(response.status_code, 200, response.data)
		bookings[0].refresh_from_db()
		self.assertEqual(bookings[0].group_session_id, other["sessions"][0]["id"])
		self.assertEqual(bookings[0].original_session_id, group["sessions"][0]["id"])
		self.assertEqual(bookings[0].base_price, Decimal("33.34"))
		for booking in bookings[1:]:
			booking.refresh_from_db()
			self.assertEqual(booking.starts_at, self.dates[(booking.visit_number or 1) - 1])
			self.assertEqual(booking.status, "booked")

	def test_separate_makeup_reserves_time_but_does_not_move_group(self):
		group = self.create_group().data
		self.enroll(group)
		booking = Booking.objects.order_by("id").first()
		moved = self.starts_at + timedelta(hours=1)
		response = self.act(booking.id, action="move", specialist_id=self.specialist.id, starts_at=moved.isoformat())
		self.assertEqual(response.status_code, 200, response.data)
		booking.refresh_from_db()
		self.assertIsNone(booking.group_session_id)
		self.assertTrue(booking.is_individual_override)
		self.assertEqual(GroupSession.objects.get(id=group["sessions"][0]["id"]).starts_at, self.starts_at)
		self.assertEqual(self.book(service=self.individual, starts_at=moved).status_code, 409)
		self.assertEqual(self.act(booking.id, action="move", specialist_id=self.specialist.id, starts_at=self.starts_at.isoformat()).status_code, 409)

	def test_schedule_cannot_remove_empty_reserved_lesson(self):
		self.create_group()
		schedule = [{**self.schedule[0], "is_day_off": True}]
		response = self.client.patch("/api/v1/partner/specialists/schedule/", {"items": [{
			"specialist_id": self.specialist.id, "working_schedule": schedule,
		}]}, format="json", **self.headers)
		self.assertEqual(response.status_code, 409, response.data)
		self.specialist.refresh_from_db()
		self.assertFalse(self.specialist.working_schedule[0]["is_day_off"])

	def test_empty_future_group_protects_service_and_teacher_from_archiving(self):
		self.create_group()
		for url, data in (
			(f"/api/v1/partner/services/{self.service.id}/", {"is_active": False}),
			(f"/api/v1/partner/specialists/{self.specialist.id}/", {"is_active": False}),
			(f"/api/v1/partner/specialists/{self.specialist.id}/", {"service_ids": [self.individual.id]}),
		):
			with self.subTest(url=url, data=data):
				response = self.client.patch(url, data, format="json", **self.headers)
				self.assertEqual(response.status_code, 409, response.data)

	def test_foreign_tenant_group_and_booking_are_not_accessible(self):
		group = self.create_group().data
		self.enroll(group)
		headers = {**self.headers, "HTTP_X_TENANT": "foreign"}
		self.assertEqual(self.client.get(f"/api/v1/partner/groups/{group['id']}/", **headers).status_code, 404)
		self.assertEqual(self.client.get("/api/v1/partner/groups/", **headers).data["items"], [])
		booking = Booking.objects.first()
		self.assertEqual(self.client.patch(f"/api/v1/partner/groups/participants/{booking.id}/", {"action": "cancel"}, format="json", **headers).status_code, 404)

	def test_unexpected_enrollment_failure_rolls_back_whole_transaction(self):
		group = self.create_group().data
		request = APIRequestFactory().post(f"/api/v1/partner/groups/{group['id']}/enroll/", {
			"request_id": str(uuid.uuid4()), "client_name": "Rollback", "client_phone": "+77009990003",
			"session_ids": [item["id"] for item in group["sessions"]],
		}, format="json", **self.headers)
		original = Booking.objects.create
		calls = 0

		def create(**kwargs):
			nonlocal calls
			calls += 1
			if calls == 2:
				raise RuntimeError("test rollback")
			return original(**kwargs)

		with patch.object(Booking.objects, "create", side_effect=create):
			with self.assertRaisesRegex(RuntimeError, "test rollback"):
				GroupEnrollView.as_view()(request, group_id=group["id"])
		self.assertFalse(Booking.objects.exists())
		self.assertFalse(BookingPass.objects.exists())
		self.assertEqual(GroupSession.objects.count(), 3)

	def lesson_action(self, session_id, **changes):
		return self.client.patch(f"/api/v1/partner/groups/sessions/{session_id}/", changes, format="json", **self.headers)

	def test_teacher_one_off_1500_to_1600_moves_only_one_lesson_and_its_clients(self):
		dates = [value.replace(hour=15) for value in self.dates]
		group = self.create_group(sessions=[value.isoformat() for value in dates]).data
		self.enroll(group)
		self.enroll(group, phone="+77009990004")
		first = group["sessions"][0]["id"]
		moved = dates[0].replace(hour=16)
		response = self.lesson_action(first, action="move", starts_at=moved.isoformat())
		self.assertEqual(response.status_code, 200, response.data)
		self.assertEqual(response.data["original_starts_at"], dates[0].isoformat())
		self.assertEqual(GroupSession.objects.get(id=first).starts_at, moved)
		self.assertEqual(list(GroupSession.objects.exclude(id=first).values_list("starts_at", flat=True)), dates[1:])
		self.assertEqual(set(Booking.objects.filter(group_session_id=first).values_list("starts_at", flat=True)), {moved})
		self.assertEqual(Booking.objects.exclude(group_session_id=first).filter(starts_at__in=dates[1:]).count(), 4)
		self.assertEqual(list(Booking.objects.filter(group_session_id=first).values_list("base_price", flat=True)), [Decimal("33.34")] * 2)
		self.assertEqual(self.book(service=self.individual, starts_at=dates[0]).status_code, 201)
		self.assertEqual(self.book(service=self.individual, starts_at=moved, phone="+77009990005").status_code, 409)

	def test_whole_lesson_move_allows_overlapping_its_old_time_but_not_other_reservations(self):
		group = self.create_group().data
		self.enroll(group)
		first = group["sessions"][0]["id"]
		moved = self.starts_at + timedelta(minutes=30)
		self.assertEqual(self.lesson_action(first, action="move", starts_at=moved.isoformat()).status_code, 200)
		conflict = self.lesson_action(first, action="move", starts_at=self.dates[1].isoformat())
		self.assertEqual(conflict.status_code, 409)
		self.assertEqual(GroupSession.objects.get(id=first).starts_at, moved)

	def test_single_client_conflict_aborts_entire_lesson_move(self):
		from .models import Specialist, SpecialistService
		group = self.create_group().data
		self.enroll(group)
		self.enroll(group, phone="+77009990004")
		other = Specialist.objects.create(tenant_slug="public", partner_profile=self.partner, full_name="Other teacher", phone="+77009990009", working_schedule=self.schedule)
		SpecialistService.objects.create(specialist=other, service=self.individual)
		moved = self.starts_at + timedelta(hours=1)
		self.assertEqual(self.book(phone="+77009990004", service=self.individual, starts_at=moved, manager_name=other.full_name).status_code, 201)
		response = self.lesson_action(group["sessions"][0]["id"], action="move", starts_at=moved.isoformat())
		self.assertEqual(response.status_code, 409, response.data)
		self.assertIn("не перенесено", response.data["message"])
		self.assertEqual(GroupSession.objects.get(id=group["sessions"][0]["id"]).starts_at, self.starts_at)
		self.assertEqual(Booking.objects.filter(group_session_id=group["sessions"][0]["id"], starts_at=self.starts_at).count(), 2)

	def test_whole_lesson_cancel_keeps_other_lessons_and_individual_makeup(self):
		group = self.create_group().data
		self.enroll(group)
		self.enroll(group, phone="+77009990004")
		first, other = list(Booking.objects.filter(group_session_id=group["sessions"][0]["id"]).order_by("id"))
		makeup = self.starts_at + timedelta(hours=1)
		self.assertEqual(self.act(first.id, action="move", specialist_id=self.specialist.id, starts_at=makeup.isoformat()).status_code, 200)
		response = self.lesson_action(group["sessions"][0]["id"], action="cancel")
		self.assertEqual(response.status_code, 200)
		first.refresh_from_db()
		other.refresh_from_db()
		self.assertEqual(first.status, "booked")
		self.assertEqual(first.starts_at, makeup)
		self.assertEqual(other.status, "cancelled")
		self.assertEqual(Booking.objects.exclude(id__in=[first.id, other.id]).filter(status="booked").count(), 4)
		self.assertEqual(self.book(service=self.individual).status_code, 201)
		self.assertEqual(self.lesson_action(group["sessions"][0]["id"], action="cancel").status_code, 200)
		self.assertEqual(self.enroll(group, phone="+77009990005").status_code, 409)

	def test_empty_lesson_can_be_moved_and_cancelled_without_creating_clients(self):
		group = self.create_group().data
		first = group["sessions"][0]["id"]
		moved = self.starts_at + timedelta(hours=1)
		self.assertEqual(self.lesson_action(first, action="move", starts_at=moved.isoformat()).status_code, 200)
		self.assertEqual(self.lesson_action(first, action="cancel").status_code, 200)
		self.assertFalse(Booking.objects.exists())
		self.assertEqual(GroupSession.objects.count(), 3)
		self.assertEqual(self.book(service=self.individual, starts_at=moved).status_code, 201)

	def test_lesson_edit_protects_history_and_tenant(self):
		group = self.create_group().data
		self.enroll(group)
		booking = Booking.objects.first()
		self.act(booking.id, action="complete")
		self.assertEqual(self.lesson_action(group["sessions"][0]["id"], action="cancel").status_code, 409)
		headers = {**self.headers, "HTTP_X_TENANT": "foreign"}
		self.assertEqual(self.client.patch(f"/api/v1/partner/groups/sessions/{group['sessions'][0]['id']}/", {"action": "cancel"}, format="json", **headers).status_code, 404)

	def test_migration_preserves_legacy_group_bookings_and_prices(self):
		import importlib
		from django.apps import apps
		from django.db import connection
		from .views import calculate_booking_pricing
		pricing = calculate_booking_pricing([self.service], self.specialist, self.starts_at, allow_discount=False)
		bookings = [Booking.objects.create(
			tenant_slug="public", partner_profile=self.partner, service_name=self.service.name,
			manager_name=self.specialist.full_name, starts_at=self.starts_at,
			client_name="Legacy client", client_phone=f"+7700999000{index}", **pricing,
		) for index in (3, 4)]
		migration = importlib.import_module("partner_api.migrations.0028_backfill_group_sessions")
		migration.backfill_groups(apps, connection.schema_editor())
		migration.backfill_groups(apps, connection.schema_editor())
		self.assertEqual(BookingGroup.objects.count(), 1)
		self.assertEqual(GroupSession.objects.count(), 1)
		for booking in bookings:
			booking.refresh_from_db()
			self.assertIsNotNone(booking.group_session_id)
			self.assertEqual(booking.group_session_id, booking.original_session_id)
			self.assertEqual(booking.pricing_details, pricing["pricing_details"])
			self.assertEqual(booking.final_price, pricing["final_price"])

	def test_migration_attaches_older_unpriced_group_without_rewriting_history(self):
		import importlib
		from django.apps import apps
		from django.db import connection
		booking = Booking.objects.create(
			tenant_slug="public", partner_profile=self.partner, service_name=self.service.name,
			manager_name=self.specialist.full_name, starts_at=self.starts_at,
			client_name="Legacy unpriced client", client_phone="+77009990003",
		)
		migration = importlib.import_module("partner_api.migrations.0028_backfill_group_sessions")
		migration.backfill_groups(apps, connection.schema_editor())
		booking.refresh_from_db()
		self.assertIsNotNone(booking.group_session_id)
		self.assertEqual(booking.final_price, Decimal("0.00"))
		self.assertEqual(booking.pricing_details, [])
		self.assertEqual(booking.group_session.base_price, self.service.price)
		response = self.act(booking.id, action="move", specialist_id=self.specialist.id, starts_at=(self.starts_at + timedelta(hours=1)).isoformat())
		self.assertEqual(response.status_code, 200, response.data)
		booking.refresh_from_db()
		self.assertEqual(booking.final_price, Decimal("0.00"))
		self.assertEqual(booking.pricing_details[0]["duration_minutes"], 60)
