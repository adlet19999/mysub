import uuid
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from common_api.models import PartnerProfile
from partner_api.models import Booking, Category, Service, ServiceKind, Specialist, SpecialistService
from .models import CustomerProfile, PhoneChallenge
from .views import issue_tokens
from .models import BookingResource, BookingReview, MobileBookingRecord, MobileContent, MobileNotification
from unittest.mock import patch
from .tests import image_upload
from tempfile import TemporaryDirectory
from pathlib import Path
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from .models import CustomerChild
from partner_api.models import BookingGroup, GroupSession, BusinessTable
from common_api.models import BusinessCategory


@override_settings(MOBILE_OTP_MODE="test", MOBILE_OTP_ALLOW_TEST_MODE=True, MOBILE_OTP_RESEND_SECONDS=0)
class PhoneFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.phone = "+77000001001"

    def send(self):
        return self.client.post("/api/v1/mobile/auth/send-code/", {"phone": self.phone}, format="json")

    def verify(self, code="11111"):
        return self.client.post("/api/v1/mobile/auth/verify-code/", {"phone": self.phone, "code": code}, format="json")

    def test_unified_flow_creates_then_authenticates_without_fabricated_consent(self):
        self.assertEqual(self.send().status_code, 200)
        first = self.verify()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["Cache-Control"], "no-store")
        self.assertTrue(first.data["is_new_user"])
        self.assertFalse(first.data["user"]["agreement_accepted"])
        self.send()
        second = self.verify()
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.data["is_new_user"])
        self.assertEqual(first.data["user"]["id"], second.data["user"]["id"])
        self.assertEqual(CustomerProfile.objects.count(), 1)

    def test_code_is_single_use_and_expires(self):
        self.send()
        self.assertEqual(self.verify().status_code, 200)
        self.assertEqual(self.verify().data["error"]["code"], "OTP_USED")
        self.send()
        PhoneChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verify().data["error"]["code"], "OTP_EXPIRED")

    def test_attempt_limit(self):
        self.send()
        for _ in range(5):
            self.assertEqual(self.verify("00000").status_code, 401)
        self.assertEqual(self.verify().status_code, 429)

    @override_settings(MOBILE_OTP_MODE="disabled")
    def test_unconfigured_sms_is_not_fake_success(self):
        self.assertEqual(self.send().status_code, 503)
        self.assertFalse(PhoneChallenge.objects.exists())

    def test_logout_revokes_access_and_refresh(self):
        self.send()
        response = self.verify()
        tokens = response.data["tokens"]
        headers = {"HTTP_AUTHORIZATION": f"Bearer {tokens['access_token']}"}
        self.assertEqual(self.client.post("/api/v1/mobile/auth/logout/", {}, format="json", **headers).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/mobile/users/me/", **headers).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/mobile/auth/refresh/", {"refresh_token": tokens["refresh_token"]}, format="json").status_code, 401)

    def test_config_does_not_advertise_unimplemented_features(self):
        response = self.client.get("/api/v1/mobile/config/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["profile_required_fields"], ["name", "city_id"])
        self.assertEqual(response.data["avatar_max_bytes"], 5242880)
        self.assertFalse(response.data["features"]["checkout"])
        self.assertFalse(response.data["features"]["push"])
        self.assertFalse(response.data["features"]["resource_nightly_pricing"])

    def test_development_challenge_is_not_reported_as_delivered_sms(self):
        response = self.send()
        self.assertEqual(response.data["delivery_mode"], "test")
        self.assertEqual(response.data["message"], "Development challenge created")

    @override_settings(MOBILE_OTP_RESEND_SECONDS=60)
    def test_resend_delay_is_persisted_and_has_retry_header(self):
        self.assertEqual(self.send().status_code, 200)
        response = self.send()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["error"]["code"], "OTP_RESEND_LIMIT")
        self.assertTrue(1 <= response.data["error"]["retry_after"] <= 60)
        self.assertEqual(response["Retry-After"], str(response.data["error"]["retry_after"]))

    @override_settings(MOBILE_OTP_MODE="provider", MOBILE_SMS_SENDER="synthetic.sender")
    def test_provider_must_explicitly_acknowledge_acceptance(self):
        for result in (None, False):
            with patch("mobile_api.otp.import_string") as load_sender:
                load_sender.return_value.return_value = result
                with self.assertLogs("mobile_api.otp", level="ERROR"):
                    response = self.send()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.data["error"]["code"], "SMS_DELIVERY_FAILED")
            self.assertFalse(PhoneChallenge.objects.exclude(code_hash="").exists())

    @override_settings(MOBILE_OTP_MODE="provider", MOBILE_SMS_SENDER="synthetic.sender")
    def test_provider_failure_is_explicit_and_does_not_activate_code(self):
        from .otp import SMSDeliveryError
        with patch("mobile_api.otp.import_string") as load_sender:
            load_sender.return_value.side_effect = SMSDeliveryError("Synthetic provider failure")
            with self.assertLogs("mobile_api.otp", level="ERROR"):
                response = self.send()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(PhoneChallenge.objects.exclude(code_hash="").exists())

    @override_settings(MOBILE_OTP_MODE="provider", MOBILE_SMS_SENDER="synthetic.sender")
    def test_acknowledged_provider_challenge_stores_hash_and_verifies_once(self):
        with patch("mobile_api.otp.import_string") as load_sender:
            load_sender.return_value.return_value = True
            self.assertEqual(self.send().status_code, 200)
            code = load_sender.return_value.call_args.kwargs["code"]
        challenge = PhoneChallenge.objects.get(phone=self.phone)
        self.assertNotEqual(challenge.code_hash, code)
        self.assertEqual(self.verify(code).status_code, 200)
        self.assertEqual(self.verify(code).data["error"]["code"], "OTP_USED")

    def test_invalid_explicit_language_does_not_silently_create_account_or_consume_code(self):
        self.send()
        response = self.client.post("/api/v1/mobile/auth/verify-code/",
                                     {"phone": self.phone, "code": "11111", "language": "unsupported"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["details"][0]["field"], "language")
        self.assertFalse(CustomerProfile.objects.exists())
        self.assertEqual(self.verify().status_code, 200)

    def test_unauthorized_response_has_bearer_challenge(self):
        response = self.client.get("/api/v1/mobile/users/me/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Bearer")

    def test_malformed_signed_account_id_returns_unauthorized_not_database_error(self):
        import jwt
        from django.conf import settings
        for subject in ("not-an-id", "999999999999999999999"):
            token = jwt.encode({"sub": subject, "type": "access", "iss": "mysub-mobile-api",
                                "aud": "mysub-mobile-app", "exp": timezone.now() + timedelta(minutes=1)},
                               settings.MOBILE_JWT_SECRET, algorithm="HS256")
            response = self.client.get("/api/v1/mobile/users/me/", HTTP_AUTHORIZATION=f"Bearer {token}")
            self.assertEqual(response.status_code, 401)

    def test_openapi_documents_binary_upload_typed_pass_and_error_contract(self):
        from drf_spectacular.validation import validate_schema
        response = self.client.get("/api/v1/mobile/schema/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        schema = response.data
        validate_schema(schema)
        paths, components = schema["paths"], schema["components"]["schemas"]
        upload = paths["/api/v1/mobile/users/me/avatar/"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
        self.assertEqual(components[upload["$ref"].rsplit("/", 1)[-1]]["properties"]["file"]["format"], "binary")
        self.assertIn("visits", components["BookingPass"]["properties"])
        self.assertIn("/api/v1/mobile/bookings/quote/", paths)
        self.assertNotIn("get", paths["/api/v1/mobile/bookings/quote/"])
        self.assertIn("200", paths["/api/v1/mobile/bookings/"]["post"]["responses"])
        self.assertIn("default", paths["/api/v1/mobile/users/me/"]["patch"]["responses"])
        for path in ("users/me/", "favorites/", "notifications/", "bookings/requests/{request_id}/"):
            operation = paths[f"/api/v1/mobile/{path}"]["get"]
            self.assertEqual(operation["security"], [{"MobileBearer": []}])
            self.assertIn("401", operation["responses"])
        error = paths["/api/v1/mobile/auth/send-code/"]["post"]["responses"]["503"]["content"]["application/json"]["schema"]
        self.assertEqual(error["$ref"], "#/components/schemas/MobileErrorResponse")


class BookingContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        user = User.objects.create_user(username="mobile-contract", first_name="Айша")
        self.customer = CustomerProfile.objects.create(user=user, phone="+77000001002")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(self.customer)['access_token']}"}
        partner_user = User.objects.create_user(username="mobile-contract-partner")
        self.partner = PartnerProfile.objects.create(user=partner_user, phone="+77000001003", business_category="Красота")
        category = Category.objects.create(tenant_slug="public", name="Красота")
        kind = ServiceKind.objects.create(tenant_slug="public", category=category, name="Стрижка")
        self.service = Service.objects.create(tenant_slug="public", partner_profile=self.partner, category=category, kind=kind, name="Стрижка", price="5000.00")
        day = timezone.localdate() + timedelta(days=1)
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][day.weekday()]
        self.specialist = Specialist.objects.create(tenant_slug="public", partner_profile=self.partner, full_name="Мастер", working_schedule=[{"day": weekday, "start_time": "09:00", "end_time": "18:00", "breaks": []}])
        SpecialistService.objects.create(specialist=self.specialist, service=self.service)
        self.starts_at = timezone.make_aware(datetime.combine(day, time(10)))
        self.payload = {"partner_id": self.partner.id, "service_id": self.service.id, "specialist_id": self.specialist.id, "starts_at": self.starts_at.isoformat(), "request_id": str(uuid.uuid4()), "comment": "Без звонка"}

    def create(self, payload=None):
        return self.client.post("/api/v1/mobile/bookings/", payload or self.payload, format="json", **self.headers)

    def test_ordinary_create_replays_and_retains_identifiers_and_comment(self):
        first = self.create()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data["service_id"], self.service.id)
        self.assertEqual(first.data["specialist_id"], self.specialist.id)
        self.assertEqual(first.data["comment"], "Без звонка")
        self.assertEqual(first.data["duration_minutes"], 60)
        self.assertEqual(self.create().status_code, 200)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(self.create({**self.payload, "comment": "Другой"}).status_code, 409)

    def test_reschedule_is_atomic_and_revision_checked(self):
        first = self.create()
        url = f"/api/v1/mobile/bookings/{first.data['id']}/reschedule/"
        target = self.starts_at + timedelta(hours=2)
        payload = {"starts_at": target.isoformat(), "revision": first.data["revision"], "request_id": str(uuid.uuid4())}
        moved = self.client.post(url, payload, format="json", **self.headers)
        self.assertEqual(moved.status_code, 200)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Booking.objects.get().starts_at, target)
        self.assertEqual(self.client.post(url, payload, format="json", **self.headers).status_code, 200)
        stale = {**payload, "request_id": str(uuid.uuid4()), "starts_at": (target + timedelta(hours=1)).isoformat()}
        self.assertEqual(self.client.post(url, stale, format="json", **self.headers).status_code, 409)
        self.assertEqual(Booking.objects.get().starts_at, target)

    def test_unknown_status_is_neither_completed_nor_cancellable(self):
        first = self.create()
        Booking.objects.filter(id=first.data["id"]).update(status="future_unknown")
        history = self.client.get("/api/v1/mobile/bookings/", **self.headers)
        booking = history.data["data"][0]
        self.assertEqual(booking["status_group"], "unknown")
        self.assertFalse(booking["is_cancellable"])

    def test_favorite_repeats_and_clear_all(self):
        url = f"/api/v1/mobile/favorites/{self.partner.id}/"
        self.assertEqual(self.client.put(url, {}, format="json", **self.headers).status_code, 200)
        self.assertEqual(self.client.put(url, {}, format="json", **self.headers).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/mobile/favorites/", **self.headers).data["total"], 1)
        self.assertEqual(self.client.delete("/api/v1/mobile/favorites/", **self.headers).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/mobile/favorites/", **self.headers).data["total"], 0)

    def test_review_requires_completion_and_replays_identically(self):
        first = self.create()
        url = f"/api/v1/mobile/bookings/{first.data['id']}/review/"
        payload = {"rating": 5, "comment": "Спасибо"}
        self.assertEqual(self.client.post(url, payload, format="json", **self.headers).status_code, 409)
        Booking.objects.filter(id=first.data["id"]).update(status="completed")
        self.assertEqual(self.client.post(url, payload, format="json", **self.headers).status_code, 201)
        self.assertEqual(self.client.post(url, payload, format="json", **self.headers).status_code, 200)
        self.assertEqual(self.client.post(url, {**payload, "rating": 4}, format="json", **self.headers).status_code, 409)

    def test_quote_does_not_reserve_and_changed_price_rejects_creation(self):
        quote = self.client.post("/api/v1/mobile/bookings/quote/", self.payload, format="json", **self.headers)
        self.assertEqual(quote.status_code, 200, quote.data)
        self.assertEqual(quote.data["final_price"], "5000.00")
        self.assertFalse(quote.data["is_reserved"])
        self.assertEqual(Booking.objects.count(), 0)
        self.service.price = "6000.00"
        self.service.save()
        self.assertEqual(self.create({**self.payload, "expected_final_price": "5000.00"}).status_code, 409)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(MobileNotification.objects.count(), 0)

    def test_missing_price_is_not_a_free_booking(self):
        self.service.price = None
        self.service.save()
        self.assertEqual(self.create().data["error"]["code"], "PRICE_NOT_CONFIGURED")
        self.assertFalse(Booking.objects.exists())

    def test_occupied_reschedule_preserves_original_and_siblings(self):
        first = self.create()
        target = self.starts_at + timedelta(hours=2)
        other = self.create({**self.payload, "request_id": str(uuid.uuid4()), "starts_at": target.isoformat()})
        url = f"/api/v1/mobile/bookings/{first.data['id']}/reschedule/"
        response = self.client.post(url, {"starts_at": target.isoformat(), "revision": first.data["revision"], "request_id": str(uuid.uuid4())}, format="json", **self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Booking.objects.get(id=first.data["id"]).starts_at, self.starts_at)
        self.assertEqual(Booking.objects.get(id=other.data["id"]).starts_at, target)

    def test_stable_specialist_identity_blocks_slot_after_rename(self):
        self.assertEqual(self.create().status_code, 201)
        self.specialist.full_name = "Новое имя"
        self.specialist.save()
        conflict = self.create({**self.payload, "request_id": str(uuid.uuid4())})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(Booking.objects.count(), 1)

    def test_unknown_status_and_naive_dates_do_not_become_bookable_success(self):
        self.assertEqual(self.create({**self.payload, "starts_at": self.starts_at.replace(tzinfo=None).isoformat()}).status_code, 400)
        self.assertEqual(self.create({**self.payload, "comment": "x" * 2001}).status_code, 400)
        self.assertEqual(self.create({**self.payload, "unexpected": "value"}).status_code, 400)
        self.assertFalse(Booking.objects.exists())

    def test_medical_entries_are_atomic_and_independently_addressable(self):
        self.partner.business_category = "Медицинские центры"
        self.partner.save()
        entries = [
            {"service_id": self.service.id, "specialist_id": self.specialist.id, "starts_at": self.starts_at.isoformat(), "comment": "Первый"},
            {"service_id": self.service.id, "specialist_id": self.specialist.id, "starts_at": (self.starts_at + timedelta(hours=1)).isoformat(), "comment": "Второй"},
        ]
        payload = {"partner_id": self.partner.id, "request_id": str(uuid.uuid4()), "entries": entries}
        response = self.create(payload)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["booking_group"]["entries"]), 2)
        self.assertEqual(self.create(payload).status_code, 200)
        sibling = response.data["booking_group"]["entries"][1]
        self.assertEqual(self.client.post(f"/api/v1/mobile/bookings/{sibling['id']}/cancel/", {}, format="json", **self.headers).status_code, 200)
        self.assertEqual(Booking.objects.get(id=response.data["id"]).status, "booked")

    def test_invalid_second_medical_entry_rolls_back_everything(self):
        self.partner.business_category = "Медицинские центры"
        self.partner.save()
        response = self.create({"partner_id": self.partner.id, "request_id": str(uuid.uuid4()), "entries": [
            {"service_id": self.service.id, "specialist_id": self.specialist.id, "starts_at": self.starts_at.isoformat()},
            {"service_id": self.service.id, "specialist_id": 999999, "starts_at": (self.starts_at + timedelta(hours=1)).isoformat()},
        ]})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(MobileNotification.objects.count(), 0)

    def test_medical_visit_entries_cannot_cross_calendar_dates(self):
        self.partner.business_category = "Медицинские центры"
        self.partner.save()
        response = self.create({"partner_id": self.partner.id, "request_id": str(uuid.uuid4()), "entries": [
            {"service_id": self.service.id, "specialist_id": self.specialist.id, "starts_at": self.starts_at.isoformat()},
            {"service_id": self.service.id, "specialist_id": self.specialist.id,
             "starts_at": (self.starts_at + timedelta(days=1)).isoformat()},
        ]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "ENTRY_DATE")
        self.assertFalse(Booking.objects.exists())
        self.assertFalse(MobileNotification.objects.exists())

    def test_statistics_use_almaty_month_boundaries_not_utc_month(self):
        first_day = timezone.localdate().replace(day=1)
        boundary = timezone.make_aware(datetime.combine(first_day, time(0, 5)))
        for starts_at in (boundary, boundary - timedelta(minutes=10)):
            Booking.objects.create(tenant_slug="public", partner_profile=self.partner, service_name="История",
                                   client_phone=self.customer.phone, starts_at=starts_at, status="completed",
                                   base_price="1000.00", final_price="950.00", discount_amount="50.00")
        response = self.client.get("/api/v1/mobile/bookings/statistics/", {"month": first_day.strftime("%Y-%m")}, **self.headers)
        self.assertEqual(response.data["all_time"]["completed_visits"], 2)
        self.assertEqual(response.data["selected_month"]["completed_visits"], 1)
        self.assertEqual(response.data["selected_month"]["savings"], "50.00")

    def test_resource_is_owned_capacity_checked_and_reserved_exclusively(self):
        self.service.category.name = "Фотостудии"
        self.service.category.save()
        resource = BookingResource.objects.create(partner=self.partner, name="Зал", kind="hall", capacity=2, working_schedule=self.specialist.working_schedule)
        resource.services.add(self.service)
        payload = {key: value for key, value in self.payload.items() if key != "specialist_id"}
        payload.update(resource_id=resource.id, party_size=2)
        first = self.create(payload)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["resource"]["party_size"], 2)
        self.assertIsNone(first.data["specialist_id"])
        self.assertEqual(self.create({**payload, "request_id": str(uuid.uuid4())}).status_code, 409)
        self.assertEqual(self.create({**payload, "request_id": str(uuid.uuid4()), "starts_at": (self.starts_at + timedelta(hours=2)).isoformat(), "party_size": 3}).status_code, 400)
        moved = self.client.post(f"/api/v1/mobile/bookings/{first.data['id']}/reschedule/",
                                 {"starts_at": (self.starts_at + timedelta(hours=2)).isoformat(), "revision": first.data["revision"], "request_id": str(uuid.uuid4())},
                                 format="json", **self.headers)
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual(Booking.objects.count(), 1)

    def test_carwash_vehicle_is_required_and_persisted(self):
        self.service.category.name = "Автомойки"
        self.service.category.save()
        self.assertEqual(self.create().data["error"]["code"], "VEHICLE_REQUIRED")
        result = self.create({**self.payload, "vehicle": {"model": "Toyota", "registration_plate": " 123 abc "}})
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["vehicle"], {"model": "Toyota", "registration_plate": "123 ABC"})

    def test_pass_prices_are_typed_and_cancel_keeps_siblings(self):
        self.service.is_pass = True
        self.service.visit_count = 2
        self.service.pass_price_mode = "total"
        self.service.price = "0.03"
        self.service.save()
        visits = [self.starts_at.isoformat(), (self.starts_at + timedelta(hours=2)).isoformat()]
        payload = {**self.payload, "visits": visits, "expected_final_price": "0.03"}
        quote = self.client.post("/api/v1/mobile/bookings/quote/", payload, format="json", **self.headers)
        self.assertEqual(quote.status_code, 200, quote.data)
        self.assertEqual([visit["base_price"] for visit in quote.data["visits"]], ["0.02", "0.01"])
        result = self.create(payload)
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["booking_pass"]["visit_count"], 2)
        self.assertEqual([visit["final_price"] for visit in result.data["booking_pass"]["visits"]], ["0.02", "0.01"])
        second_id = result.data["booking_pass"]["visits"][1]["id"]
        self.client.post(f"/api/v1/mobile/bookings/{second_id}/cancel/", {}, format="json", **self.headers)
        self.assertEqual(Booking.objects.get(id=result.data["id"]).status, "booked")

    def test_transferred_pass_visit_does_not_expose_other_accounts_visits(self):
        self.service.is_pass, self.service.visit_count = True, 2
        self.service.save()
        original = self.create({**self.payload, "visits": [self.starts_at.isoformat(), (self.starts_at + timedelta(hours=2)).isoformat()]})
        self.assertEqual(original.status_code, 201)
        first_id, second_id = [item["id"] for item in original.data["booking_pass"]["visits"]]
        first = Booking.objects.get(id=first_id)
        first.status = "completed"
        first.save()
        other = CustomerProfile.objects.create(user=User.objects.create_user(username="pass-assignee", first_name="Новый"),
                                               phone="+77000001016")
        second = Booking.objects.get(id=second_id)
        second.client_phone = other.phone
        second.save()
        headers = {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(other)['access_token']}"}
        transferred = self.client.get("/api/v1/mobile/bookings/", **headers).data["data"][0]["booking_pass"]
        self.assertEqual([item["id"] for item in transferred["visits"]], [second_id])
        self.assertEqual(transferred["completed_visits"], 0)
        self.assertEqual(transferred["owned_visit_count"], 1)
        self.assertFalse(transferred["is_complete"])
        remaining = self.client.get("/api/v1/mobile/bookings/", **self.headers).data["data"][0]["booking_pass"]
        self.assertEqual([item["id"] for item in remaining["visits"]], [first_id])

    @override_settings(MOBILE_OTP_MODE="test", MOBILE_OTP_ALLOW_TEST_MODE=True, MOBILE_OTP_RESEND_SECONDS=0)
    def test_phone_change_preserves_history_and_invalidates_old_phone_challenge(self):
        original = self.create()
        old_phone = self.customer.phone
        new_phone = "+77000001009"
        self.client.post("/api/v1/mobile/auth/send-code/", {"phone": old_phone}, format="json")
        request = self.client.post("/api/v1/mobile/users/me/phone/request/", {"phone": new_phone}, format="json", **self.headers)
        self.assertEqual(request.status_code, 200, request.data)
        confirm = self.client.post("/api/v1/mobile/users/me/phone/confirm/", {"phone": new_phone, "code": "11111"}, format="json", **self.headers)
        self.assertEqual(confirm.status_code, 200, confirm.data)
        self.assertEqual(confirm.data["user"]["id"], str(self.customer.id))
        self.assertEqual(self.client.get("/api/v1/mobile/bookings/", **self.headers).data["data"][0]["id"], original.data["id"])
        self.assertEqual(self.create().status_code, 200)
        stale = self.client.post("/api/v1/mobile/auth/verify-code/", {"phone": old_phone, "code": "11111"}, format="json")
        self.assertEqual(stale.status_code, 401)
        self.client.post("/api/v1/mobile/auth/send-code/", {"phone": old_phone}, format="json")
        new_holder = self.client.post("/api/v1/mobile/auth/verify-code/", {"phone": old_phone, "code": "11111"}, format="json")
        self.assertEqual(new_holder.status_code, 200, new_holder.data)
        self.assertNotEqual(new_holder.data["user"]["id"], str(self.customer.id))

    def test_foreign_account_cannot_read_cancel_move_review_or_replay(self):
        original = self.create()
        other_user = User.objects.create_user(username="other-mobile-contract", first_name="Другой")
        other = CustomerProfile.objects.create(user=other_user, phone="+77000001008")
        headers = {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(other)['access_token']}"}
        identity = original.data["id"]
        self.assertEqual(self.client.get("/api/v1/mobile/bookings/", **headers).data["data"], [])
        self.assertEqual(self.client.post(f"/api/v1/mobile/bookings/{identity}/cancel/", {}, format="json", **headers).status_code, 404)
        self.assertEqual(self.client.post(f"/api/v1/mobile/bookings/{identity}/review/", {"rating": 5}, format="json", **headers).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/mobile/bookings/requests/{self.payload['request_id']}/", **headers).status_code, 404)
        move = {"starts_at": (self.starts_at + timedelta(hours=2)).isoformat(), "revision": original.data["revision"], "request_id": str(uuid.uuid4())}
        self.assertEqual(self.client.post(f"/api/v1/mobile/bookings/{identity}/reschedule/", move, format="json", **headers).status_code, 404)

    def test_public_reviews_hide_pending_and_aggregate_all_published(self):
        original = self.create()
        Booking.objects.filter(id=original.data["id"]).update(status="completed")
        review = self.client.post(f"/api/v1/mobile/bookings/{original.data['id']}/review/", {"rating": 5, "comment": "Спасибо"}, format="json", **self.headers)
        url = f"/api/v1/mobile/catalog/partners/{self.partner.id}/reviews/"
        self.assertEqual(self.client.get(url).data["rating_count"], 0)
        BookingReview.objects.filter(id=review.data["id"]).update(state="published")
        public = self.client.get(url).data
        self.assertEqual(public["rating_count"], 1)
        self.assertEqual(public["rating"], 5)
        self.assertNotIn("booking_id", public["data"][0])
        self.assertNotIn("customer_id", public["data"][0])
        self.assertEqual(self.client.get(url + "?limit=0").status_code, 400)

    def test_notifications_repeat_read_and_preferences_do_not_hide_feed(self):
        self.create()
        feed = self.client.get("/api/v1/mobile/notifications/?limit=1", **self.headers)
        self.assertEqual(feed.status_code, 200)
        self.assertEqual(feed.data["unread_count"], 1)
        identity = feed.data["data"][0]["id"]
        url = f"/api/v1/mobile/notifications/{identity}/read/"
        self.assertEqual(self.client.post(url, {}, format="json", **self.headers).data["unread_count"], 0)
        self.assertEqual(self.client.post(url, {}, format="json", **self.headers).data["unread_count"], 0)
        preferences = self.client.patch("/api/v1/mobile/notifications/preferences/", {"delivery_enabled": False, "offers_enabled": True}, format="json", **self.headers)
        self.assertFalse(preferences.data["delivery_enabled"])
        self.assertTrue(preferences.data["offers_enabled"])
        self.assertEqual(self.client.get("/api/v1/mobile/notifications/", **self.headers).data["total"], 1)

    def test_statistics_use_explicit_completion_and_exact_money(self):
        original = self.create()
        Booking.objects.filter(id=original.data["id"]).update(status="done", discount_amount="12.34", final_price="4987.66")
        stats = self.client.get("/api/v1/mobile/bookings/statistics/", {"month": self.starts_at.strftime("%Y-%m")}, **self.headers)
        self.assertEqual(stats.data["all_time"]["completed_visits"], 1)
        self.assertEqual(stats.data["selected_month"]["savings"], "12.34")
        Booking.objects.filter(id=original.data["id"]).update(status="cancelled")
        self.assertEqual(self.client.get("/api/v1/mobile/bookings/statistics/", **self.headers).data["all_time"]["completed_visits"], 0)
        self.assertEqual(self.client.get("/api/v1/mobile/bookings/statistics/?month=bad", **self.headers).status_code, 400)

    def test_profile_revision_omissions_and_eighteenth_birthday(self):
        profile = self.client.get("/api/v1/mobile/users/me/", **self.headers)
        stale = profile.data["revision"]
        self.client.patch("/api/v1/mobile/users/me/", {"email": "client@example.test"}, format="json", **self.headers)
        rejected = self.client.patch("/api/v1/mobile/users/me/", {"name": "Новое", "revision": stale}, format="json", **self.headers)
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(self.client.get("/api/v1/mobile/users/me/", **self.headers).data["name"], "Айша")
        today = timezone.localdate()
        birthday = today.replace(year=today.year - 18, day=28 if (today.month, today.day) == (2, 29) else today.day)
        response = self.client.patch("/api/v1/mobile/users/me/", {"children": [{"name": "Амир", "date_of_birth": birthday.isoformat()}]}, format="json", **self.headers)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.patch("/api/v1/mobile/users/me/", {"phone": "+77000001111"}, format="json", **self.headers).status_code, 400)

    def test_avatar_binary_delivery_and_failed_profile_patch_preserve_old_image(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            uploaded = self.client.post("/api/v1/mobile/users/me/avatar/", {"file": image_upload()}, format="multipart", **self.headers)
            self.assertEqual(uploaded.status_code, 200)
            from urllib.parse import urlsplit
            path = urlsplit(uploaded.data["avatar_url"]).path
            image = self.client.get(path)
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image["Content-Type"], "image/webp")
            self.assertTrue(b"".join(image.streaming_content))
            rejected = self.client.patch("/api/v1/mobile/users/me/", {"avatar_url": "", "children": [{"name": "Амир", "date_of_birth": "2099-01-01"}]}, format="json", **self.headers)
            self.assertEqual(rejected.status_code, 422)
            self.assertTrue((Path(directory) / "customer_avatars" / path.rsplit("/", 1)[-1]).exists())
            with self.captureOnCommitCallbacks(execute=True):
                replacement = self.client.post("/api/v1/mobile/users/me/avatar/", {"file": image_upload()}, format="multipart", **self.headers)
            self.assertEqual(replacement.status_code, 200)
            self.assertFalse((Path(directory) / "customer_avatars" / path.rsplit("/", 1)[-1]).exists())

    def test_content_is_explicitly_unconfigured_until_approved(self):
        result = self.client.get("/api/v1/mobile/content/?kind=legal").data
        self.assertFalse(result["is_configured"])
        MobileContent.objects.create(key="privacy", kind="legal", language="ru", title="Approved test policy", body="Synthetic acceptance content", version="test-1", effective_at=timezone.now(), is_published=False)
        self.assertEqual(self.client.get("/api/v1/mobile/content/").data["data"], [])

    def test_avatar_accepts_exact_byte_limit_and_rejects_one_more(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            contents = image_upload().read()
            boundary = contents + b"\0" * (5242880 - len(contents))
            accepted = self.client.post("/api/v1/mobile/users/me/avatar/",
                                       {"file": SimpleUploadedFile("photo.png", boundary, content_type="image/png")},
                                       format="multipart", **self.headers)
            self.assertEqual(accepted.status_code, 200)
            rejected = self.client.post("/api/v1/mobile/users/me/avatar/",
                                       {"file": SimpleUploadedFile("photo.png", boundary + b"\0", content_type="image/png")},
                                       format="multipart", **self.headers)
            self.assertEqual(rejected.status_code, 413)
            self.assertEqual(self.client.get("/api/v1/mobile/users/me/", **self.headers).data["avatar_url"], accepted.data["avatar_url"])

    def test_failed_avatar_database_save_removes_new_file(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            with patch.object(CustomerProfile, "save", side_effect=DatabaseError("Synthetic write failure")):
                with self.assertLogs("django.request", level="ERROR"), self.assertRaises(DatabaseError):
                    self.client.post("/api/v1/mobile/users/me/avatar/", {"file": image_upload()},
                                     format="multipart", **self.headers)
            self.assertEqual(list((Path(directory) / "customer_avatars").glob("*.webp")), [])

    def test_newborn_today_is_accepted_and_future_birth_is_rejected(self):
        today = timezone.localdate()
        accepted = self.client.patch("/api/v1/mobile/users/me/",
                                     {"children": [{"name": "О’Коннор", "date_of_birth": today.isoformat()}]},
                                     format="json", **self.headers)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.data["children"][0]["age"], 0)
        rejected = self.client.patch("/api/v1/mobile/users/me/",
                                     {"children": [{"name": "Амир", "date_of_birth": (today + timedelta(days=1)).isoformat()}]},
                                     format="json", **self.headers)
        self.assertEqual(rejected.status_code, 422)

    def test_crm_reassignment_does_not_transfer_private_attendee_comment_or_review(self):
        original = self.create()
        booking = Booking.objects.get(id=original.data["id"])
        record = booking.mobile_record
        record.attendee = {"type": "child", "name": "Прежний участник"}
        record.vehicle = {"model": "Private"}
        record.batch_id = uuid.uuid4()
        record.save()
        booking.status = "completed"
        booking.save()
        self.client.post(f"/api/v1/mobile/bookings/{booking.id}/review/",
                         {"rating": 5, "comment": "Приватный отзыв"}, format="json", **self.headers)
        other = CustomerProfile.objects.create(user=User.objects.create_user(username="assigned-mobile", first_name="Новый"),
                                               phone="+77000001015")
        booking.client_phone = other.phone
        booking.save()
        headers = {"HTTP_AUTHORIZATION": f"Bearer {issue_tokens(other)['access_token']}"}
        transferred = self.client.get("/api/v1/mobile/bookings/", **headers).data["data"][0]
        self.assertEqual(transferred["attendee"], {})
        self.assertEqual(transferred["vehicle"], {})
        self.assertEqual(transferred["comment"], "")
        self.assertIsNone(transferred["booking_group"])
        self.assertIsNone(transferred["review"])
        response = self.client.post(f"/api/v1/mobile/bookings/{booking.id}/review/",
                                    {"rating": 5, "comment": "Приватный отзыв"}, format="json", **headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get("/api/v1/mobile/bookings/", **self.headers).data["total"], 0)

    def test_two_children_take_distinct_group_seats_and_inactive_teacher_is_hidden(self):
        self.partner.business_category = "Кружки и курсы"
        self.partner.save()
        self.service.category, _ = Category.objects.get_or_create(tenant_slug="public", name="Кружки и курсы")
        BusinessCategory.objects.update_or_create(name="Кружки и курсы", defaults={"allows_group_services": True})
        self.service.service_type = "group"
        self.service.details = {"require_occurrence": True, "max_people": 2, "audience": "child"}
        self.service.save()
        group = BookingGroup.objects.create(tenant_slug="public", partner_profile=self.partner, name="Класс",
                                            service=self.service, specialist=self.specialist, capacity=2,
                                            duration_minutes=90, price="5000.00")
        session = GroupSession.objects.create(group=group, starts_at=self.starts_at, base_price="5000.00")
        url = f"/api/v1/mobile/catalog/partners/{self.partner.id}/group-sessions/"
        self.assertTrue(self.client.get(url, {"service_id": self.service.id}).data["data"][0]["is_bookable"])
        original_price = self.service.price
        self.service.price = None
        self.service.save()
        self.assertFalse(self.client.get(url, {"service_id": self.service.id}).data["data"][0]["is_bookable"])
        self.service.price = original_price
        self.service.save()
        today = timezone.localdate()
        birthday = today.replace(year=today.year - 10, day=min(today.day, 28))
        children = [CustomerChild.objects.create(customer=self.customer, name=name, date_of_birth=birthday) for name in ("Амир", "Алия")]
        for child in children:
            response = self.create({**self.payload, "request_id": str(uuid.uuid4()), "group_session_id": session.id,
                                    "attendee": {"type": "child", "child_id": child.id}})
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["duration_minutes"], 90)
            self.assertEqual(Booking.objects.get(id=response.data["id"]).group_session_id, session.id)
        url = f"/api/v1/mobile/catalog/partners/{self.partner.id}/group-sessions/"
        data = self.client.get(url, {"service_id": self.service.id}).data["data"][0]
        self.assertEqual(data["remaining_seats"], 0)
        self.assertFalse(data["is_bookable"])
        oversold = self.create({**self.payload, "request_id": str(uuid.uuid4()), "group_session_id": session.id,
                                "attendee": {"type": "child", "child_id": children[0].id}})
        self.assertEqual(oversold.status_code, 409)
        self.assertEqual(oversold.data["error"]["code"], "SLOT_UNAVAILABLE")
        self.assertEqual(Booking.objects.count(), 2)
        self.assertEqual(self.client.get(f"/api/v1/mobile/catalog/partners/{self.partner.id}/specialists/{self.specialist.id}/availability/",
                                         {"service_id": self.service.id, "date": self.starts_at.date().isoformat()}).status_code, 400)
        self.specialist.is_active = False
        self.specialist.save()
        self.assertEqual(self.client.get(url, {"service_id": self.service.id}).data["data"], [])

    def test_reschedule_uses_child_snapshot_but_revalidates_target_age(self):
        today = timezone.localdate()
        birthday = today.replace(year=today.year - 10, day=min(today.day, 28))
        child = CustomerChild.objects.create(customer=self.customer, name="Амир", date_of_birth=birthday)
        original = self.create({**self.payload, "attendee": {"type": "child", "child_id": child.id}})
        self.assertEqual(original.status_code, 201)
        child.delete()
        url = f"/api/v1/mobile/bookings/{original.data['id']}/reschedule/"
        payload = {"starts_at": (self.starts_at + timedelta(hours=2)).isoformat(),
                   "request_id": str(uuid.uuid4()), "revision": original.data["revision"]}
        moved = self.client.post(url, payload, format="json", **self.headers)
        self.assertEqual(moved.status_code, 200, moved.data)
        self.service.details = {"audience": "child", "min_age": 11}
        self.service.save()
        rejected = self.client.post(url, {**payload, "starts_at": (self.starts_at + timedelta(hours=3)).isoformat(),
                                         "request_id": str(uuid.uuid4()), "revision": moved.data["revision"]},
                                    format="json", **self.headers)
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(Booking.objects.get(id=original.data["id"]).starts_at, self.starts_at + timedelta(hours=2))

    def test_restaurant_quote_create_and_reschedule_keep_two_hour_table_snapshot(self):
        self.partner.business_category = "Кафе и рестораны"
        self.partner.save()
        table = BusinessTable.objects.create(tenant_slug="public", partner_profile=self.partner, name="Стол 1", capacity=4)
        payload = {key: value for key, value in self.payload.items() if key != "specialist_id"}
        payload["party_size"] = 3
        quote = self.client.post("/api/v1/mobile/bookings/quote/", payload, format="json", **self.headers)
        self.assertEqual(quote.status_code, 200, quote.data)
        self.assertFalse(quote.data["is_reserved"])
        self.assertEqual(quote.data["table_id"], table.id)
        self.assertEqual(Booking.objects.count(), 0)
        original = self.create(payload)
        self.assertEqual(original.status_code, 201, original.data)
        self.assertEqual(original.data["duration_minutes"], 120)
        self.assertIsNone(original.data["specialist_id"])
        table.name, table.capacity = "Новое название", 6
        table.save()
        history = self.client.get("/api/v1/mobile/bookings/", **self.headers).data["data"][0]
        self.assertEqual(history["restaurant"]["table_snapshot"]["capacity"], 4)
        self.assertEqual(history["restaurant"]["table_snapshot"]["name"], "Стол 1")
        target = self.starts_at + timedelta(hours=3)
        moved = self.client.post(f"/api/v1/mobile/bookings/{original.data['id']}/reschedule/",
                                 {"starts_at": target.isoformat(), "request_id": str(uuid.uuid4()), "revision": original.data["revision"]},
                                 format="json", **self.headers)
        self.assertEqual(moved.status_code, 200, moved.data)
        booking = Booking.objects.get(id=original.data["id"])
        self.assertEqual(booking.ends_at, target + timedelta(hours=2))
        self.assertEqual(moved.data["restaurant"]["table_snapshot"]["capacity"], 6)
