from django.contrib.auth.models import User
from rest_framework.test import APIClient

from django.test import TestCase

from partner_api.models import Manager

from .models import PartnerProfile


class ArchivedManagerLoginTests(TestCase):
	def test_archived_manager_cannot_log_in(self):
		partner = User.objects.create_user(username="partner@example.com", email="partner@example.com", password="password123")
		partner_profile = PartnerProfile.objects.create(user=partner, phone="+77001112233", user_type="partner")
		manager = User.objects.create_user(username="manager@example.com", email="manager@example.com", password="password123")
		PartnerProfile.objects.create(user=manager, phone="+77001112234", user_type="manager")
		Manager.objects.create(
			tenant_slug="public",
			partner_profile=partner_profile,
			full_name="Архивный менеджер",
			phone="+77001112234",
			email="manager@example.com",
			is_active=False,
		)

		response = APIClient().post(
			"/api/v1/auth/login/",
			{"username": "manager@example.com", "password": "password123"},
			format="json",
		)

		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.data["message"], "Аккаунт менеджера заблокирован")
