from django.contrib import admin

from .models import Booking, BusinessTable, Category, Manager, Service, ServiceKind, Specialist, SpecialistService


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
	list_display = ("name", "tenant_slug", "is_active", "created_at")
	list_filter = ("tenant_slug", "is_active")
	search_fields = ("name",)


@admin.register(ServiceKind)
class ServiceKindAdmin(admin.ModelAdmin):
	list_display = ("name", "category", "tenant_slug", "is_active", "created_at")
	list_filter = ("tenant_slug", "is_active", "category")
	search_fields = ("name", "category__name")


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
	list_display = (
		"name",
		"category",
		"kind",
		"tenant_slug",
		"price",
		"duration_minutes",
		"discount_percent",
		"is_subscription",
		"is_active",
	)
	list_filter = ("tenant_slug", "is_active", "is_subscription", "is_promo", "category", "kind")
	search_fields = ("name", "description")


@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
	list_display = ("full_name", "phone", "email", "tenant_slug", "is_active", "created_at")
	list_filter = ("tenant_slug", "is_active")
	search_fields = ("full_name", "phone", "email")


@admin.register(Specialist)
class SpecialistAdmin(admin.ModelAdmin):
	list_display = ("full_name", "description", "phone", "email", "tenant_slug", "is_active", "created_at")
	list_filter = ("tenant_slug", "is_active")
	search_fields = ("full_name", "description", "phone", "email")


@admin.register(SpecialistService)
class SpecialistServiceAdmin(admin.ModelAdmin):
	list_display = ("specialist", "service", "created_at")
	list_filter = ("service__category",)
	search_fields = ("specialist__full_name", "service__name")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
	list_display = ("service_name", "manager_name", "client_name", "starts_at", "status", "tenant_slug")
	list_filter = ("tenant_slug", "status")
	search_fields = ("service_name", "client_name", "client_phone")


@admin.register(BusinessTable)
class BusinessTableAdmin(admin.ModelAdmin):
	list_display = ("name", "partner_profile", "tenant_slug", "is_active", "created_at")
	list_filter = ("tenant_slug", "is_active")
	search_fields = ("name", "description")
