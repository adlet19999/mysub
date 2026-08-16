from django.db import migrations, models


def copy_primary_offer_photo(apps, schema_editor):
    BusinessOffer = apps.get_model("partner_api", "BusinessOffer")
    for offer in BusinessOffer.objects.exclude(photo_url=""):
        offer.photo_urls = [offer.photo_url]
        offer.save(update_fields=["photo_urls"])


class Migration(migrations.Migration):
    dependencies = [
        ("partner_api", "0022_business_offer_display_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="businessoffer",
            name="photo_urls",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(copy_primary_offer_photo, migrations.RunPython.noop),
    ]