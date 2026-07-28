from django.db import migrations


def remove_duplicate_specialists(apps, schema_editor):
    Specialist = apps.get_model("partner_api", "Specialist")
    SpecialistService = apps.get_model("partner_api", "SpecialistService")

    seen = set()
    duplicate_ids = []

    for specialist in Specialist.objects.order_by("id"):
        service_ids = tuple(
            SpecialistService.objects.filter(specialist_id=specialist.id)
            .order_by("service_id")
            .values_list("service_id", flat=True)
        )
        key = (
            specialist.tenant_slug,
            specialist.partner_profile_id,
            specialist.full_name.strip().lower(),
            specialist.description.strip().lower(),
            specialist.phone.strip(),
            specialist.email.strip().lower(),
            service_ids,
        )
        if key in seen:
            duplicate_ids.append(specialist.id)
        else:
            seen.add(key)

    if duplicate_ids:
        Specialist.objects.filter(id__in=duplicate_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("partner_api", "0017_seed_two_level_service_catalog"),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_specialists, migrations.RunPython.noop),
    ]