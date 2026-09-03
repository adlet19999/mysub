from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partner_api", "0023_business_offer_photo_urls"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="base_price",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="booking",
            name="discount_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="booking",
            name="final_price",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="booking",
            name="pricing_details",
            field=models.JSONField(blank=True, default=list),
        ),
    ]