from django.db import migrations, models
import django.db.models.deletion


CITIES = [
    "Алматы", "Астана", "Шымкент", "Актобе", "Актау", "Атырау", "Балхаш",
    "Жезказган", "Караганда", "Кокшетау", "Костанай", "Кызылорда", "Конаев",
    "Кульсары", "Павлодар", "Петропавловск", "Семей", "Талдыкорган", "Тараз",
    "Туркестан", "Уральск", "Усть-Каменогорск",
]


def seed_cities_and_migrate_profiles(apps, schema_editor):
    City = apps.get_model("mobile_api", "City")
    CustomerProfile = apps.get_model("mobile_api", "CustomerProfile")
    cities_by_name = {}
    for index, name in enumerate(CITIES, start=1):
        city, _ = City.objects.get_or_create(name=name, defaults={"display_order": index})
        cities_by_name[name.lower()] = city

    for profile in CustomerProfile.objects.exclude(city_name=""):
        city = cities_by_name.get(profile.city_name.strip().lower())
        if city:
            profile.city = city
            profile.save(update_fields=["city"])


class Migration(migrations.Migration):
    dependencies = [
        ("mobile_api", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="City",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("display_order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ("display_order", "name")},
        ),
        migrations.RenameField(
            model_name="customerprofile",
            old_name="city_id",
            new_name="legacy_city_id",
        ),
        migrations.AddField(
            model_name="customerprofile",
            name="city",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="customer_profiles", to="mobile_api.city"),
        ),
        migrations.RunPython(seed_cities_and_migrate_profiles, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="customerprofile",
            name="legacy_city_id",
        ),
        migrations.RemoveField(
            model_name="customerprofile",
            name="city_name",
        ),
    ]