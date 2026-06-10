from django.db import models


class Category(models.Model):
	tenant_slug = models.CharField(max_length=80, db_index=True)
	name = models.CharField(max_length=120)
	parent = models.ForeignKey("self", on_delete=models.CASCADE, related_name="children", null=True, blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["tenant_slug", "name", "parent"], name="uniq_category_name_per_parent")
		]


class ServiceKind(models.Model):
	tenant_slug = models.CharField(max_length=80, db_index=True)
	category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="service_kinds")
	name = models.CharField(max_length=120)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["tenant_slug", "category", "name"], name="uniq_service_kind_per_category")
		]


class Service(models.Model):
	tenant_slug = models.CharField(max_length=80, db_index=True)
	partner_profile = models.ForeignKey(
		"common_api.PartnerProfile",
		on_delete=models.CASCADE,
		related_name="services",
		null=True,
		blank=True,
	)
	name = models.CharField(max_length=120)
	category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="services")
	kind = models.ForeignKey(ServiceKind, on_delete=models.SET_NULL, null=True, blank=True, related_name="services")
	details = models.JSONField(default=dict, blank=True)
	description = models.TextField(blank=True, default="")
	duration_minutes = models.PositiveIntegerField(default=60)
	price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	discount_percent = models.PositiveSmallIntegerField(default=0)
	is_subscription = models.BooleanField(default=True)
	image_url = models.URLField(blank=True, default="")
	is_promo = models.BooleanField(default=False)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)


class Manager(models.Model):
	tenant_slug = models.CharField(max_length=80, db_index=True)
	partner_profile = models.ForeignKey(
		"common_api.PartnerProfile",
		on_delete=models.CASCADE,
		related_name="managers",
		null=True,
		blank=True,
	)
	full_name = models.CharField(max_length=120)
	phone = models.CharField(max_length=32)
	email = models.EmailField(blank=True, default="")
	photo_base64 = models.TextField(blank=True, default="")
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)


class Specialist(models.Model):
	tenant_slug = models.CharField(max_length=80, db_index=True)
	partner_profile = models.ForeignKey(
		"common_api.PartnerProfile",
		on_delete=models.CASCADE,
		related_name="specialists",
		null=True,
		blank=True,
	)
	full_name = models.CharField(max_length=120)
	description = models.TextField(blank=True, default="")
	phone = models.CharField(max_length=32)
	email = models.EmailField(blank=True, default="")
	photo_base64 = models.TextField(blank=True, default="")
	working_schedule = models.JSONField(default=list, blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)


class SpecialistServiceKind(models.Model):
	specialist = models.ForeignKey(Specialist, on_delete=models.CASCADE, related_name="capabilities")
	service_kind = models.ForeignKey(ServiceKind, on_delete=models.CASCADE, related_name="specialist_capabilities")
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["specialist", "service_kind"], name="uniq_specialist_service_kind")
		]


class Booking(models.Model):
	tenant_slug = models.CharField(max_length=80, db_index=True)
	partner_profile = models.ForeignKey(
		"common_api.PartnerProfile",
		on_delete=models.CASCADE,
		related_name="bookings",
		null=True,
		blank=True,
	)
	service_name = models.CharField(max_length=120)
	manager_name = models.CharField(max_length=120, null=True, blank=True)
	starts_at = models.DateTimeField()
	client_name = models.CharField(max_length=120)
	client_phone = models.CharField(max_length=32)
	status = models.CharField(max_length=20, default="booked")
	created_at = models.DateTimeField(auto_now_add=True)

# Create your models here.
