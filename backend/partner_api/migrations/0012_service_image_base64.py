from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("partner_api", "0011_booking_partner_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="image_base64",
            field=models.TextField(blank=True, default=""),
        ),
    ]
