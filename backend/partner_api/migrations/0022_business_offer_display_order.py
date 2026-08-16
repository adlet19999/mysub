from django.db import migrations, models


def set_initial_offer_order(apps, schema_editor):
    BusinessOffer = apps.get_model("partner_api", "BusinessOffer")
    profiles = BusinessOffer.objects.values_list("partner_profile_id", flat=True).distinct()
    for profile_id in profiles:
        for index, offer in enumerate(
            BusinessOffer.objects.filter(partner_profile_id=profile_id).order_by("created_at", "id"),
            start=1,
        ):
            offer.display_order = index
            offer.save(update_fields=["display_order"])


class Migration(migrations.Migration):
    dependencies = [
        ("partner_api", "0021_business_offer"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessoffer",
            name="display_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(set_initial_offer_order, migrations.RunPython.noop),
    ]