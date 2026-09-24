from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from mobile_api.models import City, CustomerProfile


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