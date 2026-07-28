from django.db import migrations


def clear_previous_partner_data(apps, schema_editor):
    Service = apps.get_model("partner_api", "Service")
    Specialist = apps.get_model("partner_api", "Specialist")
    ServiceKind = apps.get_model("partner_api", "ServiceKind")
    Category = apps.get_model("partner_api", "Category")

    Service.objects.all().delete()
    Specialist.objects.all().delete()
    ServiceKind.objects.all().delete()
    Category.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("partner_api", "0014_manager_specialist_photo_url"),
    ]

    operations = [
        migrations.RunPython(clear_previous_partner_data, migrations.RunPython.noop),
    ]