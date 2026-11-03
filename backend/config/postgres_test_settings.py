"""Settings for disposable local PostgreSQL acceptance, not application serving."""
import os

from django.core.exceptions import ImproperlyConfigured

from .test_settings import *


password = os.environ.get("MYSUB_TEST_PG_PASSWORD")
if not password:
    raise ImproperlyConfigured("Set MYSUB_TEST_PG_PASSWORD for a disposable local PostgreSQL instance")

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "mysub_acceptance",
    "USER": "mysub_test",
    "PASSWORD": password,
    "HOST": "127.0.0.1",
    "PORT": os.environ.get("MYSUB_TEST_PG_PORT", "5432"),
    "CONN_MAX_AGE": 0,
    "TEST": {"NAME": "test_mysub_acceptance"},
}}
