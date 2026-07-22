from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partner_api", "0013_delete_managerservicekind"),
    ]

    operations = [
        migrations.AddField(
            model_name="manager",
            name="photo_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="specialist",
            name="photo_url",
            field=models.URLField(blank=True, default=""),
        ),
    ]