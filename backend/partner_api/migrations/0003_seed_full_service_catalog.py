from django.db import migrations


CATALOG = {
    "Кафе и рестораны": [
        {
            "service": "Завтрак",
            "duration": 60,
            "kinds": ["Континентальный", "Казахский", "Детский"],
        },
        {
            "service": "Бизнес-ланч",
            "duration": 60,
            "kinds": ["Стандарт", "Премиум", "Семейный"],
        },
        {
            "service": "Ужин",
            "duration": 90,
            "kinds": ["Романтический", "Семейный", "Банкетный"],
        },
        {
            "service": "Кофе-брейк",
            "duration": 45,
            "kinds": ["Мини", "Классический", "Расширенный"],
        },
        {
            "service": "Доставка еды",
            "duration": 45,
            "kinds": ["Экспресс", "Плановая", "Корпоративная"],
        },
    ],
    "Медицинские услуги": [
        {
            "service": "Консультация врача",
            "duration": 30,
            "kinds": ["Первичная", "Повторная", "Онлайн"],
        },
        {
            "service": "Диагностика",
            "duration": 45,
            "kinds": ["УЗИ", "ЭКГ", "Лабораторная"],
        },
        {
            "service": "Стоматология",
            "duration": 60,
            "kinds": ["Осмотр", "Лечение", "Профгигиена"],
        },
        {
            "service": "Физиотерапия",
            "duration": 40,
            "kinds": ["Электротерапия", "Магнитотерапия", "Массаж"],
        },
    ],
    "Спорт": [
        {
            "service": "Тренировка в зале",
            "duration": 60,
            "kinds": ["Индивидуальная", "Групповая", "Вводная"],
        },
        {
            "service": "Йога",
            "duration": 75,
            "kinds": ["Хатха", "Виньяса", "Для начинающих"],
        },
        {
            "service": "Плавание",
            "duration": 60,
            "kinds": ["Детское", "Взрослое", "Персональное"],
        },
        {
            "service": "Единоборства",
            "duration": 90,
            "kinds": ["Бокс", "Кикбоксинг", "ММА"],
        },
    ],
    "Автоуслуги": [
        {
            "service": "Комплексная мойка",
            "duration": 60,
            "kinds": ["Легковое авто", "Кроссовер", "Внедорожник"],
        },
        {
            "service": "Детейлинг",
            "duration": 120,
            "kinds": ["Полировка", "Химчистка", "Защитное покрытие"],
        },
        {
            "service": "Шиномонтаж",
            "duration": 45,
            "kinds": ["Сезонный", "Балансировка", "Ремонт прокола"],
        },
        {
            "service": "Диагностика авто",
            "duration": 40,
            "kinds": ["Компьютерная", "Подвеска", "Электрика"],
        },
    ],
    "Кружки и курсы": [
        {
            "service": "Языковой курс",
            "duration": 90,
            "kinds": ["Английский", "Казахский", "Китайский"],
        },
        {
            "service": "Программирование",
            "duration": 120,
            "kinds": ["Frontend", "Backend", "Python"],
        },
        {
            "service": "Подготовка к экзаменам",
            "duration": 90,
            "kinds": ["ЕНТ", "IELTS", "SAT"],
        },
        {
            "service": "Творческий кружок",
            "duration": 75,
            "kinds": ["Рисование", "Музыка", "Театр"],
        },
    ],
    "Салон красоты": [
        {
            "service": "Стрижка",
            "duration": 60,
            "kinds": ["Женская", "Мужская", "Детская"],
        },
        {
            "service": "Окрашивание",
            "duration": 120,
            "kinds": ["Тон в тон", "Сложное", "Осветление"],
        },
        {
            "service": "Маникюр",
            "duration": 75,
            "kinds": ["Классический", "Аппаратный", "С покрытием"],
        },
        {
            "service": "Косметология",
            "duration": 60,
            "kinds": ["Уход за лицом", "Пилинг", "Чистка"],
        },
    ],
    "Досуг": [
        {
            "service": "Квест-комната",
            "duration": 60,
            "kinds": ["2-4 человека", "5-8 человек", "Семейный"],
        },
        {
            "service": "VR-зона",
            "duration": 45,
            "kinds": ["Одиночная", "Парная", "Командная"],
        },
        {
            "service": "Мастер-класс",
            "duration": 90,
            "kinds": ["Кулинарный", "Творческий", "Детский"],
        },
        {
            "service": "Антикафе",
            "duration": 120,
            "kinds": ["Почасовое", "Безлимит", "Событие"],
        },
    ],
}


def seed_full_catalog(apps, schema_editor):
    Category = apps.get_model("partner_api", "Category")
    ServiceKind = apps.get_model("partner_api", "ServiceKind")
    Service = apps.get_model("partner_api", "Service")

    tenant = "public"

    for category_name, entries in CATALOG.items():
        category = Category.objects.filter(tenant_slug=tenant, name=category_name, parent=None).first()
        if not category:
            continue

        for entry in entries:
            service_name = entry["service"]
            duration = entry["duration"]

            for kind_name in entry["kinds"]:
                normalized_kind_name = f"{service_name}: {kind_name}"
                kind, _ = ServiceKind.objects.get_or_create(
                    tenant_slug=tenant,
                    category=category,
                    name=normalized_kind_name,
                    defaults={"is_active": True},
                )

                exists = Service.objects.filter(
                    tenant_slug=tenant,
                    category=category,
                    kind=kind,
                    name=service_name,
                ).exists()
                if exists:
                    continue

                Service.objects.create(
                    tenant_slug=tenant,
                    name=service_name,
                    category=category,
                    kind=kind,
                    description="",
                    duration_minutes=duration,
                    price=None,
                    discount_percent=0,
                    is_subscription=True,
                    image_url="",
                    is_promo=False,
                    is_active=True,
                )


def noop_reverse(apps, schema_editor):
    # Intentional no-op to preserve data entered or edited by admins after seeding.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("partner_api", "0002_service_catalog_and_seed"),
    ]

    operations = [
        migrations.RunPython(seed_full_catalog, noop_reverse),
    ]
