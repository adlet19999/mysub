from django.db import migrations, models


def copy_primary_business_photo(apps, schema_editor):
    PartnerProfile = apps.get_model("common_api", "PartnerProfile")
    for profile in PartnerProfile.objects.exclude(business_photo_url=""):
        profile.business_photo_urls = [profile.business_photo_url]
        profile.save(update_fields=["business_photo_urls"])


class Migration(migrations.Migration):
    dependencies = [
        ("common_api", "0004_partnerprofile_business_details"),
    ]

    operations = [
        migrations.AddField(
            model_name="partnerprofile",
            name="business_photo_urls",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(copy_primary_business_photo, migrations.RunPython.noop),
    ]