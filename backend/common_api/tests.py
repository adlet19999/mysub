from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from django.test import TestCase

from partner_api.models import Booking, Manager
from mobile_api.models import CustomerProfile, CustomerSubscription

from .models import BusinessCategory, PartnerProfile, SubscriptionPlan


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
			"/api/v1/common/auth/login/",
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

	def test_staff_user_can_manage_subscription_catalog(self):
		login = self.client.post(
			"/api/v1/common/admin/login/",
			{"username": self.staff_user.username, "password": "password123"},
			format="json",
		)
		self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['token']}")
		create_plan = self.client.post(
			"/api/v1/common/admin/subscriptions/",
			{"resource": "plans", "name": "VIP", "monthly_price": 29990, "duration_months": 12, "description": "Приоритетная запись"},
			format="json",
		)
		create_category = self.client.post(
			"/api/v1/common/admin/subscriptions/",
			{"resource": "categories", "name": "Новая категория"},
			format="json",
		)
		self.assertEqual(create_plan.status_code, 201)
		self.assertEqual(create_category.status_code, 201)
		plan = SubscriptionPlan.objects.get(name="VIP")
		archive_plan = self.client.patch(f"/api/v1/common/admin/subscriptions/plans/{plan.id}/", {"is_archived": True}, format="json")
		self.assertEqual(archive_plan.status_code, 200)
		self.assertTrue(archive_plan.data["plan"]["is_archived"])
		self.assertTrue(BusinessCategory.objects.filter(name="Новая категория").exists())

	def test_categories_share_registration_and_admin_catalog(self):
		from .views import issue_admin_token

		category = BusinessCategory.objects.get(name="Автоуслуги")
		partner = PartnerProfile.objects.create(user=self.regular_user, business_category=category.name)
		self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_admin_token(self.staff_user)}")
		detail_url = f"/api/v1/common/admin/subscriptions/categories/{category.id}/"
		response = self.client.patch(detail_url, {"name": "Автосервисы"}, format="json")
		self.assertEqual(response.status_code, 200)
		partner.refresh_from_db()
		self.assertEqual(partner.business_category, "Автосервисы")
		for archived in (True, False):
			response = self.client.patch(detail_url, {"is_archived": archived}, format="json")
			self.assertEqual(response.status_code, 200)
			public = APIClient().get("/api/v1/common/business-categories/")
			self.assertEqual(public.status_code, 200)
			self.assertEqual(any(item["id"] == category.id for item in public.data["categories"]), not archived)

	def test_archived_category_cannot_be_selected_during_registration(self):
		BusinessCategory.objects.filter(name="Автоуслуги").update(is_archived=True)
		response = self.client.post("/api/v1/common/auth/register/", {
			"full_name": "Партнёр", "phone": "+77009991122", "email": "new-partner@example.com",
			"password": "password123", "business_category": "Автоуслуги",
		}, format="json")
		self.assertEqual(response.status_code, 400)
		self.assertFalse(User.objects.filter(username="new-partner@example.com").exists())

	def test_subscription_catalog_requires_admin_token(self):
		self.assertEqual(self.client.get("/api/v1/common/admin/subscriptions/").status_code, 401)
		category = BusinessCategory.objects.first()
		self.assertEqual(self.client.patch(f"/api/v1/common/admin/subscriptions/categories/{category.id}/", {"is_archived": True}, format="json").status_code, 401)

	def test_group_category_setting_cannot_disable_active_group_services(self):
		from partner_api.models import Category, Service, ServiceKind
		from .views import issue_admin_token

		self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_admin_token(self.staff_user)}")
		category = BusinessCategory.objects.get(name="Кружки и курсы")
		self.assertTrue(category.allows_group_services)
		partner = PartnerProfile.objects.create(user=self.regular_user, business_category=category.name)
		service_category = Category.objects.get(tenant_slug="public", name=category.name)
		kind = ServiceKind.objects.filter(category=service_category).first()
		service = Service.objects.create(tenant_slug="public", partner_profile=partner, name="Курс", category=service_category, kind=kind, service_type="group", details={"min_people": 1, "max_people": 8})
		url = f"/api/v1/common/admin/subscriptions/categories/{category.id}/"
		response = self.client.patch(url, {"name": category.name, "allows_group_services": False}, format="json")
		self.assertEqual(response.status_code, 409)
		service.is_active = False
		service.save()
		response = self.client.patch(url, {"name": category.name, "allows_group_services": False}, format="json")
		self.assertEqual(response.status_code, 200)
		self.assertFalse(response.data["category"]["allows_group_services"])
		created = self.client.post("/api/v1/common/admin/subscriptions/", {"resource": "categories", "name": "Обучение", "allows_group_services": True}, format="json")
		self.assertEqual(created.status_code, 201)
		self.assertTrue(created.data["category"]["allows_group_services"])

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
