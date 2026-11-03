from django.contrib import admin
from django import forms

from .models import BookingResource, BookingReview, MobileContent


class BookingResourceForm(forms.ModelForm):
    class Meta:
        model = BookingResource
        fields = "__all__"

    def clean(self):
        data = super().clean()
        partner = data.get("partner")
        services = data.get("services")
        if partner and services is not None and any(service.partner_profile_id != partner.id for service in services):
            self.add_error("services", "Все услуги должны принадлежать выбранному партнёру")
        return data


@admin.register(BookingResource)
class BookingResourceAdmin(admin.ModelAdmin):
    form = BookingResourceForm
    list_display = ("name", "partner", "kind", "capacity", "is_active")
    list_filter = ("kind", "is_active")
    filter_horizontal = ("services",)


@admin.register(BookingReview)
class BookingReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "booking", "rating", "language", "state", "created_at")
    list_filter = ("state", "language", "rating")
    readonly_fields = ("booking", "customer", "rating", "comment", "language", "created_at")


@admin.register(MobileContent)
class MobileContentAdmin(admin.ModelAdmin):
    list_display = ("key", "kind", "language", "version", "is_published")
    list_filter = ("kind", "language", "is_published")
