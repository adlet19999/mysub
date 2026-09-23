from django.test import TestCase
from rest_framework.test import APIClient

from mobile_api.models import City, CustomerProfile


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
        city = City.objects.create(name="Алматы", display_order=1)
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
        city = City.objects.create(name="Алматы", display_order=1)
        City.objects.create(name="Архивный город", display_order=2, is_active=False)
        response = self.client.get("/api/v1/mobile/cities/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [{"id": city.id, "name": "Алматы"}])

    def test_customer_can_have_at_most_two_children(self):
        headers = self.authorization()
        for name in ("Амир", "Амина"):
            response = self.client.post(
                "/api/v1/mobile/users/me/children/",
                {"name": name, "date_of_birth": "2019-05-12"},
                format="json",
                **headers,
            )
            self.assertEqual(response.status_code, 201)
        response = self.client.post(
            "/api/v1/mobile/users/me/children/",
            {"name": "Али", "date_of_birth": "2020-05-12"},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data["error"]["code"], "MAX_CHILDREN_REACHED")

    def test_customer_can_edit_and_delete_child(self):
        headers = self.authorization()
        response = self.client.post(
            "/api/v1/mobile/users/me/children/",
            {"name": "Амир", "date_of_birth": "2019-05-12"},
            format="json",
            **headers,
        )
        child_id = response.data["id"]
        response = self.client.patch(
            f"/api/v1/mobile/users/me/children/{child_id}/",
            {"name": "Али"},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Али")
        response = self.client.delete(f"/api/v1/mobile/users/me/children/{child_id}/", **headers)
        self.assertEqual(response.status_code, 204)