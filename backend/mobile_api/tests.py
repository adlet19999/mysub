from django.test import TestCase
from rest_framework.test import APIClient

from mobile_api.models import CustomerProfile


class MobileAuthAndProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.phone = "+77001234567"

    def verify(self):
        return self.client.post(
            "/api/v1/mobile/auth/verify-code/",
            {"phone": self.phone, "code": "11111"},
            format="json",
        )

    def authorization(self):
        response = self.verify()
        return {"HTTP_AUTHORIZATION": f"Bearer {response.data['tokens']['access_token']}"}

    def test_static_sms_code_registers_customer_and_returns_jwt(self):
        response = self.verify()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_new_user"])
        self.assertIn("access_token", response.data["tokens"])
        self.assertEqual(CustomerProfile.objects.get().phone, self.phone)

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