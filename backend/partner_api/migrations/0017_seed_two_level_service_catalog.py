from django.db import migrations


CATALOG = {
    "Кафе и рестораны": ["Завтрак", "Бизнес-ланч", "Ужин", "Кофе-брейк", "Доставка еды"],
    "Медицинские услуги": ["Консультация врача", "Диагностика", "Стоматология", "Физиотерапия"],
    "Спорт": ["Тренировка в зале", "Йога", "Плавание", "Единоборства"],
    "Автоуслуги": ["Комплексная мойка", "Детейлинг", "Шиномонтаж", "Диагностика авто"],
    "Кружки и курсы": ["Языковой курс", "Программирование", "Подготовка к экзаменам", "Творческий кружок"],
    "Салон красоты": ["Стрижка", "Окрашивание", "Маникюр", "Косметология"],
    "Досуг": ["Квест-комната", "VR-зона", "Мастер-класс", "Антикафе"],
}


def seed_two_level_catalog(apps, schema_editor):
    Category = apps.get_model("partner_api", "Category")
    ServiceKind = apps.get_model("partner_api", "ServiceKind")

    for category_name, kind_names in CATALOG.items():
        category = Category.objects.create(tenant_slug="public", name=category_name, is_active=True)
        ServiceKind.objects.bulk_create([
            ServiceKind(tenant_slug="public", category=category, name=kind_name, is_active=True)
            for kind_name in kind_names
        ])


class Migration(migrations.Migration):
    dependencies = [
        ("partner_api", "0016_specialists_use_partner_services"),
    ]

    operations = [
        migrations.RunPython(seed_two_level_catalog, migrations.RunPython.noop),
    ]