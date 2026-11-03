"""Isolated SQLite tests; never use these settings to serve an application."""
from unittest.mock import patch
import secrets

with patch("dotenv.load_dotenv", return_value=False):
    from .settings import *

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
SECRET_KEY = secrets.token_urlsafe(48)
MOBILE_JWT_SECRET = secrets.token_urlsafe(48)
MOBILE_OTP_MODE = "test"
MOBILE_OTP_ALLOW_TEST_MODE = True
MOBILE_OTP_RESEND_SECONDS = 0
MOBILE_OTP_LENGTH = 5
MOBILE_SMS_TEST_CODE = "11111"
MOBILE_OTP_TTL_SECONDS = 120
MOBILE_OTP_MAX_ATTEMPTS = 5
MOBILE_PUSH_SENDER = ""
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {
    "mobile_otp_send": "10000/minute", "mobile_otp_verify": "10000/minute",
    "mobile_deletion": "10000/minute",
}}
ALLOWED_HOSTS = ["testserver", "localhost"]
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
