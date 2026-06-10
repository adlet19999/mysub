from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("partner_api", "0003_seed_full_service_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="details",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
