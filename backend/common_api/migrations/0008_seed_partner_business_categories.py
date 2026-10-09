from django.db import migrations


def seed_categories(apps, schema_editor):
    category_model = apps.get_model("common_api", "BusinessCategory")
    partner_model = apps.get_model("common_api", "PartnerProfile")
    database = schema_editor.connection.alias
    names = {
        "Кафе и рестораны", "Медицинские услуги", "Спорт", "Автоуслуги",
        "Кружки и курсы", "Салон красоты", "Досуг",
    }
    names.update(partner_model.objects.using(database).exclude(business_category="").values_list("business_category", flat=True))
    for name in sorted(names):
        if not category_model.objects.using(database).filter(name__iexact=name).exists():
            category_model.objects.using(database).create(name=name)


class Migration(migrations.Migration):
    dependencies = [("common_api", "0007_subscriptionplan_businesscategory")]
    operations = [migrations.RunPython(seed_categories, migrations.RunPython.noop)]