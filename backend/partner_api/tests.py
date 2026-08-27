from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from .models import Specialist
from .views import booking_schedule_error, default_working_schedule, normalize_working_schedule

class BookingScheduleValidationTests(TestCase):
	def setUp(self):
		self.specialist = Specialist.objects.create(
			tenant_slug="public",
			full_name="Аружан",
			phone="+77000000000",
			working_schedule=default_working_schedule(),
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

	def test_date_override_does_not_change_other_same_weekdays(self):
		schedule, error = normalize_working_schedule(default_working_schedule() + [{
			"day": "sat", "date": "2026-08-01", "is_day_off": False,
			"start_time": "09:00", "end_time": "18:00", "discount_start": "10:00", "discount_end": "16:00",
			"breaks": [],
		}])
		self.assertIsNone(error)
		self.specialist.working_schedule = schedule
		self.assertIsNone(booking_schedule_error(self.specialist, timezone.make_aware(datetime(2026, 8, 1, 10)), 60))
		self.assertEqual(booking_schedule_error(self.specialist, timezone.make_aware(datetime(2026, 8, 8, 10)), 60), "У специалиста выходной в выбранный день")
