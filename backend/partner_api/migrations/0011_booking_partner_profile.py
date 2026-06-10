from django.db import migrations, models
import django.db.models.deletion


def backfill_booking_partner_profile(apps, schema_editor):
    Booking = apps.get_model("partner_api", "Booking")
    Specialist = apps.get_model("partner_api", "Specialist")

    for booking in Booking.objects.filter(partner_profile__isnull=True).exclude(manager_name__isnull=True):
        manager_name = (booking.manager_name or "").strip()
        if not manager_name:
            continue
        matched = list(
            Specialist.objects.filter(tenant_slug=booking.tenant_slug, full_name__iexact=manager_name)[:2]
        )
        if len(matched) == 1 and matched[0].partner_profile_id:
            booking.partner_profile_id = matched[0].partner_profile_id
            booking.save(update_fields=["partner_profile"])


class Migration(migrations.Migration):

    dependencies = [
        ("common_api", "0003_partnerprofile_business_category"),
        ("partner_api", "0010_specialist_description"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="partner_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="bookings",
                to="common_api.partnerprofile",
            ),
        ),
        migrations.RunPython(backfill_booking_partner_profile, migrations.RunPython.noop),
    ]
