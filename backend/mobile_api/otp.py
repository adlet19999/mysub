import logging
import math
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import PhoneChallenge


logger = logging.getLogger(__name__)


class SMSDeliveryError(Exception):
    """SMS adapters return True on gateway acceptance or raise this on failure."""


def send_challenge(phone, purpose="signin", customer=None, session_id=""):
    mode = settings.MOBILE_OTP_MODE
    test_allowed = settings.DEBUG or settings.MOBILE_OTP_ALLOW_TEST_MODE
    if mode not in {"test", "provider"} or (mode == "test" and not test_allowed):
        return None, (503, "SMS_NOT_CONFIGURED", "Доставка SMS не настроена")
    now = timezone.now()
    challenge, _ = PhoneChallenge.objects.select_for_update().get_or_create(
        phone=phone, purpose=purpose,
        defaults={"expires_at": now, "sent_at": now - timedelta(days=1)},
    )
    retry_after = max(0, math.ceil((challenge.sent_at + timedelta(seconds=settings.MOBILE_OTP_RESEND_SECONDS) - now).total_seconds()))
    if challenge.code_hash and challenge.delivery_mode == mode and retry_after > 0:
        return None, (429, "OTP_RESEND_LIMIT", "Повторите запрос после задержки", retry_after)
    length = settings.MOBILE_OTP_LENGTH
    if not 4 <= length <= 8:
        raise ImproperlyConfigured("MOBILE_OTP_LENGTH must be between 4 and 8")
    code = settings.MOBILE_SMS_TEST_CODE if mode == "test" else "".join(secrets.choice("0123456789") for _ in range(length))
    if len(code) != length or not code.isascii() or not code.isdigit():
        raise ImproperlyConfigured("Configured test OTP does not match MOBILE_OTP_LENGTH")
    if mode == "provider":
        if not settings.MOBILE_SMS_SENDER:
            return None, (503, "SMS_NOT_CONFIGURED", "Доставка SMS не настроена")
        try:
            sender = import_string(settings.MOBILE_SMS_SENDER)
        except (ImportError, AttributeError) as exc:
            logger.error("SMS adapter cannot be loaded", exc_info=exc)
            return None, (503, "SMS_NOT_CONFIGURED", "Доставка SMS не настроена")
        try:
            accepted = sender(phone=phone, code=code, expires_in=settings.MOBILE_OTP_TTL_SECONDS)
        except SMSDeliveryError as exc:
            logger.error("SMS delivery failed (%s)", type(exc).__name__)
            return None, (503, "SMS_DELIVERY_FAILED", "Не удалось отправить SMS")
        if accepted is not True:
            logger.error("SMS adapter did not acknowledge gateway acceptance")
            return None, (503, "SMS_DELIVERY_FAILED", "Не удалось подтвердить отправку SMS")
    now = timezone.now()
    challenge.customer = customer
    challenge.session_id = session_id
    challenge.code_hash = make_password(code)
    challenge.expires_at = now + timedelta(seconds=settings.MOBILE_OTP_TTL_SECONDS)
    challenge.sent_at = now
    challenge.consumed_at = None
    challenge.attempts = 0
    challenge.delivery_mode = mode
    challenge.save()
    return challenge, None


def verify_challenge(phone, code, purpose="signin", customer=None, session_id=""):
    if settings.MOBILE_OTP_MODE not in {"test", "provider"} or (settings.MOBILE_OTP_MODE == "test" and not (settings.DEBUG or settings.MOBILE_OTP_ALLOW_TEST_MODE)):
        return None, (503, "SMS_NOT_CONFIGURED", "Доставка SMS не настроена")
    challenge = PhoneChallenge.objects.select_for_update().filter(phone=phone, purpose=purpose).first()
    if challenge is None:
        return None, (401, "OTP_NOT_REQUESTED", "Сначала запросите SMS-код")
    if challenge.delivery_mode != settings.MOBILE_OTP_MODE:
        return None, (401, "OTP_REVOKED", "Запросите новый код")
    if challenge.customer_id != (customer.id if customer else None) or challenge.session_id != session_id:
        return None, (401, "OTP_CHALLENGE_MISMATCH", "Код относится к другой сессии")
    if challenge.consumed_at:
        return None, (401, "OTP_USED", "Код уже использован")
    if challenge.expires_at <= timezone.now():
        return None, (401, "OTP_EXPIRED", "Срок действия кода истёк")
    if challenge.attempts >= settings.MOBILE_OTP_MAX_ATTEMPTS:
        return None, (429, "OTP_ATTEMPTS_EXCEEDED", "Запросите новый код")
    challenge.attempts += 1
    challenge.save(update_fields=["attempts"])
    if not check_password(code, challenge.code_hash):
        return None, (401, "INVALID_CODE", "SMS-код неверен")
    challenge.consumed_at = timezone.now()
    challenge.save(update_fields=["consumed_at"])
    return challenge, None
