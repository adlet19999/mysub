from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("common_api", "0002_partnerprofile_address_partnerprofile_company_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="partnerprofile",
            name="business_category",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
