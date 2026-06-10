from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("common_api", "0003_partnerprofile_business_category"),
        ("partner_api", "0007_manager_photo_base64"),
    ]

    operations = [
        migrations.CreateModel(
            name="Specialist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_slug", models.CharField(db_index=True, max_length=80)),
                ("full_name", models.CharField(max_length=120)),
                ("phone", models.CharField(max_length=32)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("photo_base64", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "partner_profile",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="specialists",
                        to="common_api.partnerprofile",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SpecialistServiceKind",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "service_kind",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="specialist_capabilities",
                        to="partner_api.servicekind",
                    ),
                ),
                (
                    "specialist",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="capabilities",
                        to="partner_api.specialist",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="specialistservicekind",
            constraint=models.UniqueConstraint(fields=("specialist", "service_kind"), name="uniq_specialist_service_kind"),
        ),
    ]
