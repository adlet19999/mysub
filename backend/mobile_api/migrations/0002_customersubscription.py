from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("mobile_api", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan_name", models.CharField(default="Базовая", max_length=120)),
                ("status", models.CharField(choices=[("active", "Активна"), ("paused", "Приостановлена")], default="active", max_length=20)),
                ("expires_at", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("customer", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="subscription", to="mobile_api.customerprofile")),
            ],
        ),
    ]