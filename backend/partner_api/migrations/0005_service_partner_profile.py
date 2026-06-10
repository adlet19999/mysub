from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("common_api", "0003_partnerprofile_business_category"),
        ("partner_api", "0004_service_details_json"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="partner_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="services",
                to="common_api.partnerprofile",
            ),
        ),
    ]
