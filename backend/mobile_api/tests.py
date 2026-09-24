from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from common_api.models import PartnerProfile
from mobile_api.models import City, CustomerProfile
from partner_api.models import Booking, Category, Service, ServiceKind, Specialist, SpecialistService


def image_upload():
    output = BytesIO()
    Image.new("RGB", (64, 64), "green").save(output, format="PNG")
    return SimpleUploadedFile("avatar.png", output.getvalue(), content_type="image/png")


class MobileAuthAndProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.phone = "+77001234567"

    def register(self):
        return self.client.post(
            "/api/v1/mobile/auth/register/",
            {"phone": self.phone, "code": "11111"},
            format="json",
        )

    def authorization(self):
        response = self.register()
        return {"HTTP_AUTHORIZATION": f"Bearer {response.data['tokens']['access_token']}"}

    def test_register_creates_customer_and_returns_jwt(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["is_new_user"])
        self.assertIn("access_token", response.data["tokens"])
        self.assertEqual(CustomerProfile.objects.get().phone, self.phone)

    def test_register_rejects_existing_customer(self):
        self.register()
        response = self.register()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "USER_ALREADY_EXISTS")

    def test_verify_code_logs_in_existing_customer(self):
        self.register()
        response = self.client.post(
            "/api/v1/mobile/auth/verify-code/",
            {"phone": self.phone, "code": "11111"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_new_user"])

    def test_customer_can_select_city_by_id(self):
        city, _ = City.objects.get_or_create(name="Алматы", defaults={"display_order": 1})
        headers = self.authorization()
        response = self.client.patch(
            "/api/v1/mobile/users/me/",
            {"name": "Иван", "city_id": city.id},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["city_id"], city.id)
        self.assertEqual(response.data["city_name"], "Алматы")

    def test_cities_endpoint_returns_active_cities(self):
        city, _ = City.objects.get_or_create(name="Алматы", defaults={"display_order": 1})
        archived_city = City.objects.create(name="Архивный город", display_order=2, is_active=False)
        response = self.client.get("/api/v1/mobile/cities/")
        self.assertEqual(response.status_code, 200)
        self.assertIn({"id": city.id, "name": "Алматы"}, response.data["data"])
        self.assertNotIn({"id": archived_city.id, "name": "Архивный город"}, response.data["data"])

    def test_customer_can_update_profile_and_children_in_one_request(self):
        city, _ = City.objects.get_or_create(name="Алматы", defaults={"display_order": 1})
        headers = self.authorization()
        response = self.client.patch(
            "/api/v1/mobile/users/me/",
            {
                "name": "Иван",
                "city_id": city.id,
                "avatar_url": "https://cdn.mysub.kz/avatars/user.jpg",
                "agreement_accepted": True,
                "agreement_version": "1.0",
                "children": [
                    {"name": "Амир", "date_of_birth": "2019-05-12"},
                    {"name": "Амина", "date_of_birth": "2020-05-12"},
                ],
            },
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["avatar_url"], "https://cdn.mysub.kz/avatars/user.jpg")
        self.assertTrue(response.data["agreement_accepted"])
        self.assertEqual(len(response.data["children"]), 2)

    def test_profile_replaces_children_list(self):
        headers = self.authorization()
        response = self.client.patch(
            "/api/v1/mobile/users/me/",
            {"children": [{"name": "Амир", "date_of_birth": "2019-05-12"}]},
            format="json",
            **headers,
        )
        child_id = response.data["children"][0]["id"]
        response = self.client.patch(
            "/api/v1/mobile/users/me/",
            {"children": [{"id": child_id, "name": "Али", "date_of_birth": "2019-05-12"}]},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["children"][0]["name"], "Али")

    def test_customer_cannot_set_more_than_two_children(self):
        headers = self.authorization()
        response = self.client.patch(
            "/api/v1/mobile/users/me/",
            {"children": [
                {"name": "Амир", "date_of_birth": "2019-05-12"},
                {"name": "Амина", "date_of_birth": "2020-05-12"},
                {"name": "Али", "date_of_birth": "2021-05-12"},
            ]},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data["error"]["code"], "MAX_CHILDREN_REACHED")


class MobileAvatarUploadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.media_directory = TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        registration = self.client.post(
            "/api/v1/mobile/auth/register/",
            {"phone": "+77007654321", "code": "11111"},
            format="json",
        )
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {registration.data['tokens']['access_token']}"}

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()

    def test_customer_can_upload_avatar(self):
        response = self.client.post(
            "/api/v1/mobile/users/me/avatar/",
            {"file": image_upload()},
            format="multipart",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["avatar_url"].startswith("http://testserver/api/v1/mobile/avatar-images/"))
        customer = CustomerProfile.objects.get()
        self.assertTrue(customer.avatar_url.startswith("/api/v1/mobile/avatar-images/"))
        self.assertTrue((Path(self.media_directory.name) / "customer_avatars" / customer.avatar_url.rsplit("/", 1)[-1]).exists())

    def test_avatar_upload_rejects_non_image_file(self):
        response = self.client.post(
            "/api/v1/mobile/users/me/avatar/",
            {"file": SimpleUploadedFile("avatar.txt", b"not an image", content_type="text/plain")},
            format="multipart",
            **self.headers,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "INVALID_IMAGE")

    def test_avatar_endpoint_does_not_delete_customer(self):
        response = self.client.delete("/api/v1/mobile/users/me/avatar/", **self.headers)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(CustomerProfile.objects.exists())


class MobileCatalogTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = Category.objects.create(tenant_slug="public", name="Красота")
        self.kind = ServiceKind.objects.create(tenant_slug="public", category=self.category, name="Стрижка")
        self.partner = self.create_partner("salon-active", "Салон Актив")
        self.inactive_partner = self.create_partner("salon-hidden", "Салон Скрытый", is_active=False)
        self.service = self.create_service(self.partner, "Стрижка")
        self.hidden_service = self.create_service(self.inactive_partner, "Скрытая услуга")

    def create_partner(self, username, company_name, is_active=True):
        user = User.objects.create_user(username=username, is_active=is_active)
        return PartnerProfile.objects.create(
            user=user,
            phone="+77001234567",
            company_name=company_name,
            business_category="Красота",
            city="Алматы",
        )

    def create_service(self, partner, name):
        return Service.objects.create(
            tenant_slug="public",
            partner_profile=partner,
            name=name,
            category=self.category,
            kind=self.kind,
            duration_minutes=60,
            price="5000.00",
        )

    def test_catalog_excludes_inactive_partner_and_returns_active_service(self):
        response = self.client.get("/api/v1/mobile/catalog/services/?city=Алматы")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["data"]], [self.service.id])
        self.assertEqual(response.data["data"][0]["partner_id"], self.partner.id)
        self.assertNotIn(self.hidden_service.id, [item["id"] for item in response.data["data"]])

    def test_specialists_can_be_filtered_by_service(self):
        other_service = self.create_service(self.partner, "Окрашивание")
        specialist = Specialist.objects.create(
            tenant_slug="public",
            partner_profile=self.partner,
            full_name="Анна Мастер",
            phone="+77007654321",
        )
        SpecialistService.objects.create(specialist=specialist, service=self.service)
        other_specialist = Specialist.objects.create(
            tenant_slug="public",
            partner_profile=self.partner,
            full_name="Мария Колорист",
            phone="+77001112233",
        )
        SpecialistService.objects.create(specialist=other_specialist, service=other_service)

        response = self.client.get(
            f"/api/v1/mobile/catalog/partners/{self.partner.id}/specialists/?service_id={self.service.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["data"]], [specialist.id])

    def test_availability_excludes_active_booking_but_not_cancelled_booking(self):
        requested_date = timezone.localdate() + timedelta(days=1)
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][requested_date.weekday()]
        specialist = Specialist.objects.create(
            tenant_slug="public",
            partner_profile=self.partner,
            full_name="Алина Стилист",
            phone="+77005554433",
            working_schedule=[{
                "day": weekday,
                "is_day_off": False,
                "start_time": "09:00",
                "end_time": "12:00",
                "breaks": [{"name": "Обед", "start_time": "11:00", "end_time": "11:30"}],
            }],
        )
        SpecialistService.objects.create(specialist=specialist, service=self.service)
        day_start = timezone.make_aware(datetime.combine(requested_date, time.min))
        Booking.objects.create(
            tenant_slug="public",
            partner_profile=self.partner,
            service_name=self.service.name,
            manager_name=specialist.full_name,
            starts_at=day_start + timedelta(hours=10),
            client_name="Клиент",
            client_phone="+77000000001",
        )
        Booking.objects.create(
            tenant_slug="public",
            partner_profile=self.partner,
            service_name=self.service.name,
            manager_name=specialist.full_name,
            starts_at=day_start + timedelta(hours=9),
            client_name="Отменённый клиент",
            client_phone="+77000000002",
            status="cancelled",
        )

        response = self.client.get(
            f"/api/v1/mobile/catalog/partners/{self.partner.id}/specialists/{specialist.id}/availability/",
            {"date": requested_date.isoformat(), "service_id": self.service.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["slots"], ["09:00"])
        self.assertEqual(response.data["duration_minutes"], 60)

    def test_availability_requires_valid_parameters(self):
        specialist = Specialist.objects.create(
            tenant_slug="public",
            partner_profile=self.partner,
            full_name="Наталья Мастер",
            phone="+77003334455",
        )
        SpecialistService.objects.create(specialist=specialist, service=self.service)
        response = self.client.get(
            f"/api/v1/mobile/catalog/partners/{self.partner.id}/specialists/{specialist.id}/availability/",
            {"date": "not-a-date", "service_id": self.service.id},
        )

        self.assertEqual(response.status_code, 400)


class MobileBookingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        registration = self.client.post(
            "/api/v1/mobile/auth/register/",
            {"phone": "+77008889900", "code": "11111"},
            format="json",
        )
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {registration.data['tokens']['access_token']}"}
        self.customer = CustomerProfile.objects.select_related("user").get(phone="+77008889900")
        self.customer.user.first_name = "Айша"
        self.customer.user.save(update_fields=["first_name"])

        partner_user = User.objects.create_user(username="booking-partner", is_active=True)
        self.partner = PartnerProfile.objects.create(
            user=partner_user,
            phone="+77001234567",
            company_name="Студия записи",
            business_category="Красота",
            city="Алматы",
        )
        category = Category.objects.create(tenant_slug="public", name="Красота")
        kind = ServiceKind.objects.create(tenant_slug="public", category=category, name="Стрижка")
        self.service = Service.objects.create(
            tenant_slug="public",
            partner_profile=self.partner,
            category=category,
            kind=kind,
            name="Стрижка",
            duration_minutes=60,
            price="5000.00",
        )
        self.booking_date = timezone.localdate() + timedelta(days=1)
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][self.booking_date.weekday()]
        self.specialist = Specialist.objects.create(
            tenant_slug="public",
            partner_profile=self.partner,
            full_name="Алина Стилист",
            phone="+77005554433",
            working_schedule=[{
                "day": weekday,
                "is_day_off": False,
                "start_time": "09:00",
                "end_time": "13:00",
                "breaks": [],
            }],
        )
        SpecialistService.objects.create(specialist=self.specialist, service=self.service)
        self.starts_at = timezone.make_aware(datetime.combine(self.booking_date, time(10, 0)))

    def booking_payload(self, starts_at=None):
        return {
            "partner_id": self.partner.id,
            "specialist_id": self.specialist.id,
            "service_id": self.service.id,
            "starts_at": (starts_at or self.starts_at).isoformat(),
        }

    def create_booking(self, starts_at=None):
        return self.client.post(
            "/api/v1/mobile/bookings/",
            self.booking_payload(starts_at),
            format="json",
            **self.headers,
        )

    def test_customer_can_create_list_and_cancel_booking(self):
        created = self.create_booking()

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["status"], "booked")
        self.assertEqual(created.data["final_price"], "5000.00")
        booking = Booking.objects.get(id=created.data["id"])
        self.assertEqual(booking.client_phone, self.customer.phone)
        self.assertEqual(booking.client_name, "Айша")

        listed = self.client.get("/api/v1/mobile/bookings/", **self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["id"] for item in listed.data["data"]], [booking.id])

        cancelled = self.client.post(f"/api/v1/mobile/bookings/{booking.id}/cancel/", {}, format="json", **self.headers)
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["status"], "cancelled")

        repeated_cancel = self.client.post(f"/api/v1/mobile/bookings/{booking.id}/cancel/", {}, format="json", **self.headers)
        self.assertEqual(repeated_cancel.status_code, 200)

        availability = self.client.get(
            f"/api/v1/mobile/catalog/partners/{self.partner.id}/specialists/{self.specialist.id}/availability/",
            {"date": self.booking_date.isoformat(), "service_id": self.service.id},
        )
        self.assertEqual(availability.status_code, 200)
        self.assertIn("10:00", availability.data["slots"])

    def test_booking_rejects_busy_slot_and_cannot_cancel_another_customer_booking(self):
        created = self.create_booking()
        self.assertEqual(created.status_code, 201)

        conflict = self.create_booking()
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["error"]["code"], "SLOT_UNAVAILABLE")

        other_booking = Booking.objects.create(
            tenant_slug="public",
            partner_profile=self.partner,
            service_name=self.service.name,
            manager_name=self.specialist.full_name,
            starts_at=self.starts_at + timedelta(hours=2),
            client_name="Другой клиент",
            client_phone="+77001112233",
        )
        cancellation = self.client.post(
            f"/api/v1/mobile/bookings/{other_booking.id}/cancel/",
            {},
            format="json",
            **self.headers,
        )
        self.assertEqual(cancellation.status_code, 404)
        other_booking.refresh_from_db()
        self.assertEqual(other_booking.status, "booked")
