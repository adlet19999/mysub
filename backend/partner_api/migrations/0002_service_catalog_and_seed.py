from django.db import migrations, models
import django.db.models.deletion


BUSINESS_CATEGORIES = [
    "Кафе и рестораны",
    "Медицинские услуги",
    "Спорт",
    "Автоуслуги",
    "Кружки и курсы",
    "Салон красоты",
    "Досуг",
]


def seed_catalog(apps, schema_editor):
    Category = apps.get_model("partner_api", "Category")
    ServiceKind = apps.get_model("partner_api", "ServiceKind")

    tenant = "public"
    default_kind_names = ["Индивидуальная", "Групповая"]

    for category_name in BUSINESS_CATEGORIES:
        category, _ = Category.objects.get_or_create(
            tenant_slug=tenant,
            name=category_name,
            parent=None,
            defaults={"is_active": True},
        )

        for kind_name in default_kind_names:
            ServiceKind.objects.get_or_create(
                tenant_slug=tenant,
                category=category,
                name=kind_name,
                defaults={"is_active": True},
            )


def unseed_catalog(apps, schema_editor):
    Category = apps.get_model("partner_api", "Category")
    ServiceKind = apps.get_model("partner_api", "ServiceKind")

    tenant = "public"
    categories = Category.objects.filter(tenant_slug=tenant, name__in=BUSINESS_CATEGORIES, parent=None)
    ServiceKind.objects.filter(tenant_slug=tenant, category__in=categories).delete()
    categories.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("partner_api", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="children",
                to="partner_api.category",
            ),
        ),
        migrations.CreateModel(
            name="ServiceKind",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_slug", models.CharField(db_index=True, max_length=80)),
                ("name", models.CharField(max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_kinds",
                        to="partner_api.category",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="service",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="service",
            name="discount_percent",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="service",
            name="image_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="service",
            name="is_subscription",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="service",
            name="kind",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="services",
                to="partner_api.servicekind",
            ),
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                fields=("tenant_slug", "name", "parent"),
                name="uniq_category_name_per_parent",
            ),
        ),
        migrations.AddConstraint(
            model_name="servicekind",
            constraint=models.UniqueConstraint(
                fields=("tenant_slug", "category", "name"),
                name="uniq_service_kind_per_category",
            ),
        ),
        migrations.RunPython(seed_catalog, unseed_catalog),
    ]
