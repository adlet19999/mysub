from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from django.test import TestCase

from partner_api.models import Booking, Manager
from mobile_api.models import CustomerProfile, CustomerSubscription

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

	def test_staff_user_can_block_and_unblock_partner(self):
		partner_user = User.objects.create_user(username="partner@example.com", password="password123")
		partner = PartnerProfile.objects.create(user=partner_user, phone="+77001112233", user_type="partner")
		login = self.client.post(
			"/api/v1/common/admin/login/",
			{"username": self.staff_user.username, "password": "password123"},
			format="json",
		)
		self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['token']}")

		block_response = self.client.post(
			f"/api/v1/common/admin/partners/{partner.id}/status/",
			{"is_active": False},
			format="json",
		)
		partner_user.refresh_from_db()
		self.assertEqual(block_response.status_code, 200)
		self.assertFalse(partner_user.is_active)

		unblock_response = self.client.post(
			f"/api/v1/common/admin/partners/{partner.id}/status/",
			{"is_active": True},
			format="json",
		)
		partner_user.refresh_from_db()
		self.assertEqual(unblock_response.status_code, 200)
		self.assertTrue(partner_user.is_active)

	def test_staff_user_can_read_customer_profile_and_visits(self):
		customer_user = User.objects.create_user(
			username="customer@example.com",
			email="customer@example.com",
			first_name="Клиент",
			password="password123",
		)
		customer = CustomerProfile.objects.create(user=customer_user, phone="+77005556677")
		partner_user = User.objects.create_user(username="partner@example.com", password="password123")
		partner = PartnerProfile.objects.create(
			user=partner_user,
			phone="+77001112233",
			user_type="partner",
			company_name="Тестовая компания",
		)
		Booking.objects.create(
			tenant_slug="public",
			partner_profile=partner,
			service_name="Тестовая услуга",
			starts_at=timezone.now(),
			client_name="Клиент",
			client_phone=customer.phone,
			final_price=Decimal("1500.00"),
		)
		login = self.client.post(
			"/api/v1/common/admin/login/",
			{"username": self.staff_user.username, "password": "password123"},
			format="json",
		)
		self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['token']}")

		response = self.client.get(f"/api/v1/common/admin/customers/{customer.id}/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["customer"]["name"], "Клиент")
		self.assertEqual(response.data["subscription"], None)
		self.assertEqual(response.data["visits"][0]["company"], "Тестовая компания")
		self.assertEqual(response.data["visits"][0]["final_price"], "1500.00")

	def test_staff_user_can_pause_and_extend_customer_subscription(self):
		customer_user = User.objects.create_user(username="customer@example.com", password="password123")
		customer = CustomerProfile.objects.create(user=customer_user, phone="+77005556677")
		subscription = CustomerSubscription.objects.create(
			customer=customer,
			plan_name="Базовая",
			expires_at=date(2027, 1, 1),
		)
		login = self.client.post(
			"/api/v1/common/admin/login/",
			{"username": self.staff_user.username, "password": "password123"},
			format="json",
		)
		self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['token']}")

		pause_response = self.client.post(
			f"/api/v1/common/admin/customers/{customer.id}/subscription/",
			{"action": "pause"},
			format="json",
		)
		subscription.refresh_from_db()
		self.assertEqual(pause_response.status_code, 200)
		self.assertEqual(subscription.status, CustomerSubscription.Status.PAUSED)

		extend_response = self.client.post(
			f"/api/v1/common/admin/customers/{customer.id}/subscription/",
			{"action": "extend", "expires_at": "2027-12-31"},
			format="json",
		)
		subscription.refresh_from_db()
		self.assertEqual(extend_response.status_code, 200)
		self.assertEqual(subscription.expires_at, date(2027, 12, 31))
