"""Клавиатуры (inline) для навигации по боту."""

from __future__ import annotations

import calendar
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from utils import SERVICES, format_month_ru, shift_month


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Основное меню пользователя."""
    keyboard = [
        [InlineKeyboardButton("Записаться", callback_data="menu_book")],
        [InlineKeyboardButton("Мои записи", callback_data="menu_my_appointments")],
    ]
    return InlineKeyboardMarkup(keyboard)


def check_subscription_keyboard() -> InlineKeyboardMarkup:
    """Кнопка повторной проверки подписки."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Проверить подписку", callback_data="check_subscription")]]
    )


def services_keyboard() -> InlineKeyboardMarkup:
    """Список услуг для записи."""
    keyboard = [
        [InlineKeyboardButton(service, callback_data=f"service::{idx}")]
        for idx, service in enumerate(SERVICES)
    ]
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel_flow")])
    return InlineKeyboardMarkup(keyboard)


def calendar_keyboard(year: int, month: int, min_date: date) -> InlineKeyboardMarkup:
    """
    Строит месячный календарь с навигацией.

    min_date ограничивает выбор прошедших дат.
    """
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)

    keyboard: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("◀", callback_data=f"calnav::{prev_year:04d}-{prev_month:02d}"),
            InlineKeyboardButton(format_month_ru(year, month), callback_data="calnoop"),
            InlineKeyboardButton("▶", callback_data=f"calnav::{next_year:04d}-{next_month:02d}"),
        ],
        [
            InlineKeyboardButton("Пн", callback_data="calnoop"),
            InlineKeyboardButton("Вт", callback_data="calnoop"),
            InlineKeyboardButton("Ср", callback_data="calnoop"),
            InlineKeyboardButton("Чт", callback_data="calnoop"),
            InlineKeyboardButton("Пт", callback_data="calnoop"),
            InlineKeyboardButton("Сб", callback_data="calnoop"),
            InlineKeyboardButton("Вс", callback_data="calnoop"),
        ],
    ]

    for week in weeks:
        row: list[InlineKeyboardButton] = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="calnoop"))
                continue

            current = date(year, month, day)
            if current < min_date:
                row.append(InlineKeyboardButton("·", callback_data="calnoop"))
            else:
                row.append(
                    InlineKeyboardButton(
                        str(day), callback_data=f"date::{current.isoformat()}"
                    )
                )
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel_flow")])
    return InlineKeyboardMarkup(keyboard)


def times_keyboard(time_values: list[str]) -> InlineKeyboardMarkup:
    """Свободные слоты времени."""
    keyboard = [
        [InlineKeyboardButton(value, callback_data=f"time::{value}")]
        for value in time_values
    ]
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel_flow")])
    return InlineKeyboardMarkup(keyboard)


def appointments_keyboard(appointment_ids: list[int], prefix: str) -> InlineKeyboardMarkup:
    """Клавиатура с действиями по конкретным записям."""
    keyboard = [
        [
            InlineKeyboardButton(
                f"Отменить запись ID {appointment_id}",
                callback_data=f"{prefix}::{appointment_id}",
            )
        ]
        for appointment_id in appointment_ids
    ]
    keyboard.append([InlineKeyboardButton("В меню", callback_data="go_main_menu")])
    return InlineKeyboardMarkup(keyboard)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню администратора."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Показать записи на дату", callback_data="admin_show_date")],
            [InlineKeyboardButton("Удалить запись по ID", callback_data="admin_delete")],
        ]
    )
