from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("partner_api", "0015_two_level_service_catalog"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="category",
            name="uniq_category_name_per_parent",
        ),
        migrations.RemoveField(
            model_name="category",
            name="parent",
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                fields=("tenant_slug", "name"),
                name="uniq_category_name_per_tenant",
            ),
        ),
        migrations.AlterField(
            model_name="service",
            name="kind",
            field=models.ForeignKey(on_delete=models.PROTECT, related_name="services", to="partner_api.servicekind"),
        ),
        migrations.DeleteModel(
            name="SpecialistServiceKind",
        ),
        migrations.CreateModel(
            name="SpecialistService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("service", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="specialist_assignments", to="partner_api.service")),
                ("specialist", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="capabilities", to="partner_api.specialist")),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("specialist", "service"), name="uniq_specialist_service"),
                ],
            },
        ),
    ]