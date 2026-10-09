from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("common_api", "0006_partnerprofile_must_change_password"),
    ]

    operations = [
        migrations.CreateModel(
            name="BusinessCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("is_archived", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("is_archived", "name")},
        ),
        migrations.CreateModel(
            name="SubscriptionPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("monthly_price", models.PositiveIntegerField()),
                ("duration_months", models.PositiveSmallIntegerField(default=12)),
                ("description", models.TextField(blank=True, default="")),
                ("is_archived", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("is_archived", "monthly_price", "name")},
        ),
    ]