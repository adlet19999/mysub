from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("partner_api", "0006_manager_capabilities"),
    ]

    operations = [
        migrations.AddField(
            model_name="manager",
            name="photo_base64",
            field=models.TextField(blank=True, default=""),
        ),
    ]
