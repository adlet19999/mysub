from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("partner_api", "0020_business_table"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_slug", models.CharField(db_index=True, max_length=80)),
                ("title", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True, default="")),
                ("photo_url", models.URLField(blank=True, default="")),
                ("is_subscription", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("partner_profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="business_offers", to="common_api.partnerprofile")),
            ],
        ),
    ]