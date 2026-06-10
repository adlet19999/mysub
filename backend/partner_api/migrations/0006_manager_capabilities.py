from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("common_api", "0003_partnerprofile_business_category"),
        ("partner_api", "0005_service_partner_profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="manager",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="manager",
            name="partner_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="managers",
                to="common_api.partnerprofile",
            ),
        ),
        migrations.CreateModel(
            name="ManagerServiceKind",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "manager",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="capabilities",
                        to="partner_api.manager",
                    ),
                ),
                (
                    "service_kind",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="manager_capabilities",
                        to="partner_api.servicekind",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="managerservicekind",
            constraint=models.UniqueConstraint(fields=("manager", "service_kind"), name="uniq_manager_service_kind"),
        ),
    ]
