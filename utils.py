"""Вспомогательные функции: время, слоты, форматирование."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


SERVICES = [
    "Маникюр классический",
    "Маникюр с покрытием гель-лак",
    "Педикюр",
    "Наращивание ногтей",
    "Коррекция наращивания",
]

WORK_START_HOUR = 10
WORK_END_HOUR = 20
MONTHS_RU = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


def get_timezone(tz_name: str = "Europe/Moscow") -> ZoneInfo:
    """Возвращает объект часового пояса."""
    return ZoneInfo(tz_name)


def now_moscow(tz_name: str = "Europe/Moscow") -> datetime:
    """Текущее время в указанном часовом поясе (по умолчанию Москва)."""
    return datetime.now(get_timezone(tz_name))


def build_next_days(days: int = 7, tz_name: str = "Europe/Moscow") -> list[date]:
    """Формирует список дат от сегодня на ближайшие N дней."""
    today = now_moscow(tz_name).date()
    return [today + timedelta(days=i) for i in range(days)]


def build_day_slots(target_date: date, tz_name: str = "Europe/Moscow") -> list[datetime]:
    """Формирует почасовые слоты с 10:00 до 19:00 включительно."""
    tz = get_timezone(tz_name)
    slots: list[datetime] = []
    for hour in range(WORK_START_HOUR, WORK_END_HOUR):
        slot_dt = datetime.combine(target_date, time(hour=hour, minute=0)).replace(tzinfo=tz)
        slots.append(slot_dt)
    return slots


def format_datetime_ru(dt: datetime) -> str:
    """Красиво форматирует дату и время на русском."""
    weekdays = {
        0: "Понедельник",
        1: "Вторник",
        2: "Среда",
        3: "Четверг",
        4: "Пятница",
        5: "Суббота",
        6: "Воскресенье",
    }
    return f"{weekdays[dt.weekday()]}, {dt.strftime('%d.%m.%Y')} в {dt.strftime('%H:%M')}"


def can_cancel(appointment_time: datetime, tz_name: str = "Europe/Moscow") -> bool:
    """Разрешает отмену, если до записи осталось не меньше 2 часов."""
    # SQLite часто возвращает naive datetime. Приводим его к часовому поясу проекта.
    if appointment_time.tzinfo is None:
        appointment_time = appointment_time.replace(tzinfo=get_timezone(tz_name))
    return appointment_time - now_moscow(tz_name) >= timedelta(hours=2)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Сдвигает месяц вперёд/назад на delta и возвращает (год, месяц)."""
    total = (year * 12 + (month - 1)) + delta
    new_year = total // 12
    new_month = total % 12 + 1
    return new_year, new_month


def format_month_ru(year: int, month: int) -> str:
    """Форматирует заголовок месяца на русском языке."""
    return f"{MONTHS_RU[month]} {year}"
