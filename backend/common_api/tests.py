from django.contrib.auth.models import User
from rest_framework.test import APIClient

from django.test import TestCase

from partner_api.models import Manager
from mobile_api.models import CustomerProfile

from .models import PartnerProfile


class ArchivedManagerLoginTests(TestCase):
	def test_archived_manager_cannot_log_in(self):
		partner = User.objects.create_user(username="partner@example.com", email="partner@example.com", password="password123")
		partner_profile = PartnerProfile.objects.create(user=partner, phone="+77001112233", user_type="partner")
		manager = User.objects.create_user(username="manager@example.com", email="manager@example.com", password="password123", is_active=False)
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


class AdminApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.staff_user = User.objects.create_user(
			username="admin@example.com",
			email="admin@example.com",
			password="password123",
			is_staff=True,
		)
		self.regular_user = User.objects.create_user(
			username="user@example.com",
			password="password123",
		)

	def test_regular_user_cannot_log_in_to_admin_panel(self):
		response = self.client.post(
			"/api/v1/common/admin/login/",
			{"username": self.regular_user.username, "password": "password123"},
			format="json",
		)

		self.assertEqual(response.status_code, 401)

	def test_staff_user_receives_admin_token(self):
		response = self.client.post(
			"/api/v1/common/admin/login/",
			{"username": self.staff_user.username, "password": "password123"},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertIn("token", response.data)
		self.assertEqual(response.data["admin"]["username"], self.staff_user.username)

	def test_dashboard_rejects_missing_token(self):
		response = self.client.get("/api/v1/common/admin/dashboard/")

		self.assertEqual(response.status_code, 401)

	def test_staff_user_can_read_dashboard(self):
		login = self.client.post(
			"/api/v1/common/admin/login/",
			{"username": self.staff_user.username, "password": "password123"},
			format="json",
		)
		self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['token']}")

		response = self.client.get("/api/v1/common/admin/dashboard/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["admin"]["id"], self.staff_user.id)

	def test_dashboard_returns_customer_avatar_url(self):
		customer_user = User.objects.create_user(username="customer@example.com", password="password123")
		CustomerProfile.objects.create(
			user=customer_user,
			phone="+77005556677",
			avatar_url="/api/v1/mobile/avatar-images/customer-1-avatar.webp",
		)
		login = self.client.post(
			"/api/v1/common/admin/login/",
			{"username": self.staff_user.username, "password": "password123"},
			format="json",
		)
		self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['token']}")

		response = self.client.get("/api/v1/common/admin/dashboard/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			response.data["customers"][0]["avatar_url"],
			"/api/v1/mobile/avatar-images/customer-1-avatar.webp",
		)
