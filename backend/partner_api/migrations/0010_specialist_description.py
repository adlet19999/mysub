from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("partner_api", "0009_specialist_working_schedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="specialist",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
    ]
