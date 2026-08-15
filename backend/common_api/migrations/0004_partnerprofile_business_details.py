from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("common_api", "0003_partnerprofile_business_category"),
    ]

    operations = [
        migrations.AddField(model_name="partnerprofile", name="business_photo_url", field=models.URLField(blank=True, default="")),
        migrations.AddField(model_name="partnerprofile", name="city", field=models.CharField(blank=True, default="", max_length=120)),
        migrations.AddField(model_name="partnerprofile", name="description", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="partnerprofile", name="instagram", field=models.CharField(blank=True, default="", max_length=255)),
        migrations.AddField(model_name="partnerprofile", name="website", field=models.URLField(blank=True, default="")),
        migrations.AddField(model_name="partnerprofile", name="working_hours", field=models.CharField(blank=True, default="", max_length=255)),
    ]