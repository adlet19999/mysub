from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partner_api", "0018_remove_duplicate_specialists"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="service_type",
            field=models.CharField(default="individual", max_length=20),
        ),
    ]