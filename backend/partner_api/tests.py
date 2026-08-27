from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from .models import Specialist
from .views import booking_schedule_error, default_working_schedule

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
