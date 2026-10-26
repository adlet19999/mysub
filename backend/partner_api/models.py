import uuid

from django.db import models


class Category(models.Model):
	tenant_slug = models.CharField(max_length=80, db_index=True)
	name = models.CharField(max_length=120)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["tenant_slug", "name"], name="uniq_category_name_per_tenant")
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
	kind = models.ForeignKey(ServiceKind, on_delete=models.PROTECT, related_name="services")
	details = models.JSONField(default=dict, blank=True)
	description = models.TextField(blank=True, default="")
	duration_minutes = models.PositiveIntegerField(default=60)
	service_type = models.CharField(max_length=20, default="individual")
	price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
	discount_percent = models.PositiveSmallIntegerField(default=0)
	is_subscription = models.BooleanField(default=True)
	is_pass = models.BooleanField(default=False)
	visit_count = models.PositiveSmallIntegerField(default=1)
	pass_price_mode = models.CharField(max_length=12, default="per_visit", choices=[("per_visit", "Per visit"), ("total", "Total")])
	image_url = models.URLField(blank=True, default="")
	image_base64 = models.TextField(blank=True, default="")
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
	photo_url = models.URLField(blank=True, default="")
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
	photo_url = models.URLField(blank=True, default="")
	photo_base64 = models.TextField(blank=True, default="")
	working_schedule = models.JSONField(default=list, blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)


class SpecialistService(models.Model):
	specialist = models.ForeignKey(Specialist, on_delete=models.CASCADE, related_name="capabilities")
	service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="specialist_assignments")
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["specialist", "service"], name="uniq_specialist_service")
		]


class BookingGroup(models.Model):
	tenant_slug = models.CharField(max_length=80, db_index=True)
	partner_profile = models.ForeignKey("common_api.PartnerProfile", on_delete=models.CASCADE, related_name="booking_groups")
	name = models.CharField(max_length=120)
	service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="booking_groups")
	specialist = models.ForeignKey(Specialist, on_delete=models.PROTECT, related_name="booking_groups")
	capacity = models.PositiveSmallIntegerField()
	duration_minutes = models.PositiveIntegerField()
	price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	price_mode = models.CharField(max_length=12, default="per_visit")
	request_id = models.UUIDField(default=uuid.uuid4)
	request_payload = models.JSONField(default=dict)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["partner_profile", "request_id"], name="uniq_partner_group_request"),
		]


class GroupSession(models.Model):
	group = models.ForeignKey(BookingGroup, on_delete=models.CASCADE, related_name="sessions")
	starts_at = models.DateTimeField(db_index=True)
	original_starts_at = models.DateTimeField(null=True, blank=True)
	status = models.CharField(max_length=20, default="scheduled", choices=[("scheduled", "Scheduled"), ("cancelled", "Cancelled")])
	base_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

	class Meta:
		ordering = ["starts_at", "id"]
		constraints = [
			models.UniqueConstraint(fields=["group", "starts_at"], name="uniq_group_session_start"),
		]


class BookingPass(models.Model):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	partner_profile = models.ForeignKey("common_api.PartnerProfile", on_delete=models.CASCADE, related_name="booking_passes")
	request_id = models.UUIDField()
	request_payload = models.JSONField(default=dict)
	service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="booking_passes")
	group = models.ForeignKey(BookingGroup, on_delete=models.PROTECT, related_name="enrollments", null=True, blank=True)
	visit_count = models.PositiveSmallIntegerField()
	price_mode = models.CharField(max_length=12)
	total_price = models.DecimalField(max_digits=16, decimal_places=2)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["partner_profile", "request_id"], name="uniq_partner_pass_request"),
		]


class Booking(models.Model):
	class Source(models.TextChoices):
		UNKNOWN = "unknown", "Unknown"
		MANUAL = "manual", "Manual"
		MOBILE = "mobile", "Mobile"

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
	booking_source = models.CharField(max_length=20, choices=Source.choices, default=Source.UNKNOWN)
	base_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	final_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	pricing_details = models.JSONField(default=list, blank=True)
	booking_pass = models.ForeignKey(BookingPass, on_delete=models.PROTECT, related_name="bookings", null=True, blank=True)
	visit_number = models.PositiveSmallIntegerField(null=True, blank=True)
	group_session = models.ForeignKey(GroupSession, on_delete=models.PROTECT, related_name="bookings", null=True, blank=True)
	original_session = models.ForeignKey(GroupSession, on_delete=models.PROTECT, related_name="original_bookings", null=True, blank=True)
	is_individual_override = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=["booking_pass", "visit_number"], name="uniq_pass_visit_number"),
		]


class BusinessTable(models.Model):
	tenant_slug = models.CharField(max_length=80, db_index=True)
	partner_profile = models.ForeignKey(
		"common_api.PartnerProfile",
		on_delete=models.CASCADE,
		related_name="business_tables",
	)
	name = models.CharField(max_length=120)
	description = models.TextField(blank=True, default="")
	photo_url = models.URLField(blank=True, default="")
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)


class BusinessOffer(models.Model):
	tenant_slug = models.CharField(max_length=80, db_index=True)
	partner_profile = models.ForeignKey(
		"common_api.PartnerProfile",
		on_delete=models.CASCADE,
		related_name="business_offers",
	)
	title = models.CharField(max_length=120)
	description = models.TextField(blank=True, default="")
	photo_url = models.URLField(blank=True, default="")
	photo_urls = models.JSONField(default=list, blank=True)
	is_subscription = models.BooleanField(default=False)
	is_active = models.BooleanField(default=True)
	display_order = models.PositiveIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)

# Create your models here.
