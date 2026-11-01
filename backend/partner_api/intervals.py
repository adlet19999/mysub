from math import lcm

from django.utils import timezone


def slot_interval(services, default=15):
    return lcm(*(service.slot_interval_minutes or default for service in services)) if services else default


def slot_error(services, starts_at, default=15):
    interval = slot_interval(services, default)
    local = timezone.localtime(starts_at)
    if (local.hour * 60 + local.minute) % interval or local.second or local.microsecond:
        return f"Начало записи должно соответствовать интервалу {interval} мин."
    return None
