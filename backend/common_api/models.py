from django.conf import settings
from django.db import models


class PartnerProfile(models.Model):
	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="partner_profile")
	phone = models.CharField(max_length=32)
	user_type = models.CharField(max_length=20, default="partner")
	must_change_password = models.BooleanField(default=False)
	company_name = models.CharField(max_length=200, blank=True, default="")
	address = models.CharField(max_length=255, blank=True, default="")
	business_category = models.CharField(max_length=120, blank=True, default="")
	description = models.TextField(blank=True, default="")
	city = models.CharField(max_length=120, blank=True, default="")
	working_hours = models.CharField(max_length=255, blank=True, default="")
	website = models.URLField(blank=True, default="")
	instagram = models.CharField(max_length=255, blank=True, default="")
	business_photo_url = models.URLField(blank=True, default="")
	business_photo_urls = models.JSONField(default=list, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self) -> str:
		return f"{self.user.username} ({self.user_type})"

# Create your models here.
