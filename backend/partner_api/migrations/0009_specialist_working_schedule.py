from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("partner_api", "0008_specialist_entities"),
    ]

    operations = [
        migrations.AddField(
            model_name="specialist",
            name="working_schedule",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
