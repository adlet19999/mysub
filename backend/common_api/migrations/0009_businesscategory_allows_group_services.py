from django.db import migrations, models


def preserve_group_categories(apps, schema_editor):
    category_model = apps.get_model("common_api", "BusinessCategory")
    service_model = apps.get_model("partner_api", "Service")
    database = schema_editor.connection.alias
    names = {"Кружки и курсы"}
    groups = service_model.objects.using(database).filter(service_type="group")
    names.update(groups.values_list("category__name", flat=True))
    names.update(groups.exclude(partner_profile__business_category="").values_list("partner_profile__business_category", flat=True))
    for name in names:
        if name:
            category_model.objects.using(database).get_or_create(name=name)
    category_model.objects.using(database).filter(name__in=names).update(allows_group_services=True)


class Migration(migrations.Migration):
    dependencies = [
        ("common_api", "0008_seed_partner_business_categories"),
        ("partner_api", "0024_booking_pricing_snapshot"),
    ]
    operations = [
        migrations.AddField(
            model_name="businesscategory",
            name="allows_group_services",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(preserve_group_categories, migrations.RunPython.noop),
    ]