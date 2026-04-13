"""Хендлеры Telegram-бота: пользовательские и административные сценарии."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from telegram import Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import Settings
from database import Database
from keyboards import (
    admin_menu_keyboard,
    appointments_keyboard,
    calendar_keyboard,
    check_subscription_keyboard,
    main_menu_keyboard,
    services_keyboard,
    times_keyboard,
)
from utils import SERVICES, build_day_slots, can_cancel, format_datetime_ru, now_moscow

logger = logging.getLogger(__name__)

# Состояния ConversationHandler для записи.
BOOK_SELECT_SERVICE, BOOK_SELECT_DATE, BOOK_SELECT_TIME = range(3)
# Состояния для админского диалога.
ADMIN_SELECT_DATE, ADMIN_DELETE_ID = range(100, 102)


def _get_db(context: CallbackContext) -> Database:
    """Достаём объект базы данных из bot_data."""
    return context.application.bot_data["db"]


def _get_settings(context: CallbackContext) -> Settings:
    """Достаём настройки из bot_data."""
    return context.application.bot_data["settings"]


async def notify_admin_new_appointment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service: str,
    appointment_dt: datetime,
) -> None:
    """
    Отправляет администратору уведомление о новой записи.

    Ошибки отправки не прерывают пользовательский сценарий.
    """
    settings = _get_settings(context)
    user = update.effective_user
    username_text = f"@{user.username}" if user.username else "не указан"
    text = (
        "Новая запись на услугу:\n"
        f"Клиент: {user.full_name}\n"
        f"Username: {username_text}\n"
        f"User ID: {user.id}\n"
        f"Услуга: {service}\n"
        f"Дата и время: {format_datetime_ru(appointment_dt)}"
    )
    try:
        await context.bot.send_message(chat_id=settings.admin_id, text=text)
        logger.info("Уведомление о новой записи отправлено админу: admin_id=%s", settings.admin_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось отправить уведомление админу: %s", exc)


async def my_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает Telegram ID текущего пользователя для настройки ADMIN_ID."""
    user = update.effective_user
    await update.effective_message.reply_text(
        f"Ваш Telegram ID: {user.id}\n"
        "Скопируйте это значение в ADMIN_ID в файле .env (без кавычек)."
    )


async def test_admin_notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет тестовое уведомление на ADMIN_ID для проверки конфигурации."""
    settings = _get_settings(context)
    user = update.effective_user
    text = (
        "Тест уведомления администратору.\n"
        f"Текущий ADMIN_ID в .env: {settings.admin_id}\n"
        f"Команду запустил: {user.full_name} (ID: {user.id})"
    )
    try:
        await context.bot.send_message(chat_id=settings.admin_id, text=text)
        await update.effective_message.reply_text(
            f"Тест отправлен. Бот отправил сообщение на ADMIN_ID={settings.admin_id}."
        )
    except Exception as exc:  # noqa: BLE001
        await update.effective_message.reply_text(
            f"Не удалось отправить тест на ADMIN_ID={settings.admin_id}: {exc}"
        )


async def is_user_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Проверяет подписку пользователя на канал.

    Метод get_chat_member возвращает статус участника канала.
    """
    settings = _get_settings(context)
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(
            chat_id=settings.channel_id, user_id=user_id
        )
        # В разных версиях PTB/Telegram статус владельца может приходить как creator или owner.
        return str(member.status) in {"creator", "owner", "administrator", "member"}
    except (BadRequest, Forbidden) as exc:
        logger.warning(
            "Не удалось проверить подписку (chat_id=%s, user_id=%s): %s",
            settings.channel_id,
            user_id,
            exc,
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.exception("Неожиданная ошибка при проверке подписки: %s", exc)
        return False


async def require_subscription(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text_prefix: str = ""
) -> bool:
    """
    Унифицированно требует подписку, если её нет.

    Возвращает True, если пользователь подписан.
    """
    if await is_user_subscribed(update, context):
        return True

    message = (
        f"{text_prefix}\n\nПодпишитесь на наш канал, чтобы пользоваться ботом."
        if text_prefix
        else "Подпишитесь на наш канал, чтобы пользоваться ботом."
    )
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(message, reply_markup=check_subscription_keyboard())
    else:
        await update.effective_message.reply_text(
            message, reply_markup=check_subscription_keyboard()
        )
    return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Точка входа по /start: сохраняем пользователя и проверяем подписку."""
    db = _get_db(context)
    user = update.effective_user
    await db.upsert_user(user.id, user.username, user.full_name)

    if not await require_subscription(update, context):
        return

    await update.effective_message.reply_text(
        "Добро пожаловать в бот записи на маникюр!\nВыберите действие:",
        reply_markup=main_menu_keyboard(),
    )


async def check_subscription_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Обработчик кнопки 'Проверить подписку'."""
    query = update.callback_query
    await query.answer()
    if await is_user_subscribed(update, context):
        await query.message.reply_text(
            "Подписка подтверждена. Вы в главном меню:",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await query.message.reply_text(
            "Подписка пока не обнаружена. Подпишитесь на канал и проверьте снова.",
            reply_markup=check_subscription_keyboard(),
        )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает основное меню."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text("Главное меню:", reply_markup=main_menu_keyboard())
        return

    await update.effective_message.reply_text("Главное меню:", reply_markup=main_menu_keyboard())


async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Старт процесса записи: выбор услуги."""
    db = _get_db(context)
    if not await require_subscription(update, context, "Перед записью нужно подтвердить подписку."):
        return ConversationHandler.END

    if await db.has_user_active_appointment(update.effective_user.id):
        text = (
            "У вас уже есть активная запись.\n"
            "По условиям салона одновременно доступна только одна активная запись."
        )
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(text, reply_markup=main_menu_keyboard())
        else:
            await update.effective_message.reply_text(text, reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(
            "Выберите услугу:", reply_markup=services_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            "Выберите услугу:", reply_markup=services_keyboard()
        )
    return BOOK_SELECT_SERVICE


async def book_select_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет выбранную услугу и предлагает дату."""
    settings = _get_settings(context)
    query = update.callback_query
    await query.answer()
    payload = query.data.split("::", maxsplit=1)[1]
    service_idx = int(payload)
    context.user_data["selected_service"] = SERVICES[service_idx]

    now_dt = now_moscow(settings.timezone)
    context.user_data["calendar_year"] = now_dt.year
    context.user_data["calendar_month"] = now_dt.month
    await query.message.reply_text(
        "Выберите дату:",
        reply_markup=calendar_keyboard(now_dt.year, now_dt.month, now_dt.date()),
    )
    return BOOK_SELECT_DATE


async def book_select_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает календарь и показывает свободные слоты по выбранной дате."""
    db = _get_db(context)
    settings = _get_settings(context)
    query = update.callback_query
    await query.answer()

    data = query.data
    now_dt = now_moscow(settings.timezone)

    if data == "calnoop":
        return BOOK_SELECT_DATE

    if data.startswith("calnav::"):
        ym_value = data.split("::", maxsplit=1)[1]
        year, month = ym_value.split("-")
        target_year = int(year)
        target_month = int(month)
        context.user_data["calendar_year"] = target_year
        context.user_data["calendar_month"] = target_month
        await query.edit_message_reply_markup(
            reply_markup=calendar_keyboard(target_year, target_month, now_dt.date())
        )
        return BOOK_SELECT_DATE

    date_iso = data.split("::", maxsplit=1)[1]
    selected_date = datetime.strptime(date_iso, "%Y-%m-%d").date()
    if selected_date < now_dt.date():
        await query.message.reply_text("Нельзя выбрать прошедшую дату.")
        return BOOK_SELECT_DATE
    context.user_data["selected_date"] = date_iso

    all_slots = build_day_slots(selected_date, tz_name=settings.timezone)
    day_start = all_slots[0]
    day_end = day_start + timedelta(days=1)
    taken_slots = await db.get_taken_slots(day_start, day_end)

    # Фильтруем прошедшие и занятые слоты.
    free_slot_labels = [
        slot.strftime("%H:%M")
        for slot in all_slots
        if slot not in taken_slots and slot > now_dt
    ]

    if not free_slot_labels:
        await query.message.reply_text(
            "На эту дату свободных окон нет. Выберите другую дату в календаре:",
            reply_markup=calendar_keyboard(selected_date.year, selected_date.month, now_dt.date()),
        )
        return BOOK_SELECT_DATE

    await query.message.reply_text(
        "Выберите время:", reply_markup=times_keyboard(free_slot_labels)
    )
    return BOOK_SELECT_TIME


async def book_select_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финальный шаг записи: сохраняем appointment в базе."""
    db = _get_db(context)
    settings = _get_settings(context)
    query = update.callback_query
    await query.answer()

    time_value = query.data.split("::", maxsplit=1)[1]
    date_iso = context.user_data.get("selected_date")
    service = context.user_data.get("selected_service")
    if not date_iso or not service:
        await query.message.reply_text("Сессия устарела, начните запись заново.")
        return ConversationHandler.END

    if await db.has_user_active_appointment(update.effective_user.id):
        await query.message.reply_text(
            "У вас уже есть активная запись. Сначала отмените её, если хотите выбрать другое время.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    dt = datetime.strptime(f"{date_iso} {time_value}", "%Y-%m-%d %H:%M").replace(
        tzinfo=now_moscow(settings.timezone).tzinfo
    )

    appointment = await db.create_appointment(
        user_id=update.effective_user.id, service=service, appointment_time=dt
    )
    if appointment is None:
        await query.message.reply_text(
            "К сожалению, это время уже занято. Выберите другой слот.",
            reply_markup=calendar_keyboard(dt.year, dt.month, now_moscow(settings.timezone).date()),
        )
        return BOOK_SELECT_DATE

    await query.message.reply_text(
        "Вы успешно записаны!\n"
        f"Услуга: {service}\n"
        f"Дата и время: {format_datetime_ru(dt)}",
        reply_markup=main_menu_keyboard(),
    )
    await notify_admin_new_appointment(update, context, service, dt)
    context.user_data.pop("selected_date", None)
    context.user_data.pop("selected_service", None)
    return ConversationHandler.END


async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена текущего диалога записи."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(
            "Действие отменено. Возвращаю в меню.", reply_markup=main_menu_keyboard()
        )
    else:
        await update.effective_message.reply_text(
            "Действие отменено. Возвращаю в меню.", reply_markup=main_menu_keyboard()
        )
    return ConversationHandler.END


async def my_appointments_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает активные записи пользователя."""
    db = _get_db(context)
    appointments = await db.get_user_active_appointments(update.effective_user.id)
    if not appointments:
        await update.effective_message.reply_text(
            "У вас пока нет активных записей.", reply_markup=main_menu_keyboard()
        )
        return

    lines = [
        f"ID {a.id}: {a.service} — {format_datetime_ru(a.appointment_time)}"
        for a in appointments
    ]
    await update.effective_message.reply_text(
        "Ваши активные записи:\n"
        + "\n".join(lines)
        + "\n\nДля отмены нажмите кнопку ниже или используйте /cancelappointment ID",
        reply_markup=appointments_keyboard([a.id for a in appointments], "cancel_appointment"),
    )


async def my_appointments_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает записи через кнопку меню."""
    query = update.callback_query
    await query.answer()
    db = _get_db(context)
    appointments = await db.get_user_active_appointments(update.effective_user.id)
    if not appointments:
        await query.message.reply_text(
            "У вас пока нет активных записей.", reply_markup=main_menu_keyboard()
        )
        return

    lines = [
        f"ID {a.id}: {a.service} — {format_datetime_ru(a.appointment_time)}"
        for a in appointments
    ]
    await query.message.reply_text(
        "Ваши активные записи:\n"
        + "\n".join(lines)
        + "\n\nДля отмены нажмите кнопку ниже или используйте /cancelappointment ID",
        reply_markup=appointments_keyboard([a.id for a in appointments], "cancel_appointment"),
    )


async def cancel_appointment_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Отмена записи по команде:
    /cancelappointment <ID>
    """
    db = _get_db(context)
    settings = _get_settings(context)
    args = context.args

    if not args or not args[0].isdigit():
        await update.effective_message.reply_text(
            "Использование: /cancelappointment ID\n"
            "Пример: /cancelappointment 12"
        )
        return

    appointment_id = int(args[0])
    appointment = await db.get_appointment_by_id(appointment_id)
    if appointment is None or appointment.user_id != update.effective_user.id:
        await update.effective_message.reply_text("Запись не найдена.")
        return

    if not can_cancel(appointment.appointment_time, settings.timezone):
        await update.effective_message.reply_text(
            "Отмена невозможна: до начала записи осталось меньше 2 часов."
        )
        return

    cancelled = await db.cancel_appointment(appointment_id)
    if cancelled:
        await update.effective_message.reply_text(
            "Запись успешно отменена.", reply_markup=main_menu_keyboard()
        )
    else:
        await update.effective_message.reply_text("Не удалось отменить запись.")


async def cancel_appointment_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Отмена выбранной записи пользователем."""
    db = _get_db(context)
    settings = _get_settings(context)
    query = update.callback_query
    await query.answer()

    appointment_id = int(query.data.split("::", maxsplit=1)[1])
    appointment = await db.get_appointment_by_id(appointment_id)
    if appointment is None or appointment.user_id != update.effective_user.id:
        await query.message.reply_text("Запись не найдена.")
        return

    if not can_cancel(appointment.appointment_time, settings.timezone):
        await query.message.reply_text(
            "Отмена невозможна: до начала записи осталось меньше 2 часов."
        )
        return

    cancelled = await db.cancel_appointment(appointment_id)
    if cancelled:
        await query.message.reply_text(
            "Запись успешно отменена.", reply_markup=main_menu_keyboard()
        )
    else:
        await query.message.reply_text("Не удалось отменить запись.")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вход в админ-панель по /admin."""
    settings = _get_settings(context)
    if update.effective_user.id != settings.admin_id:
        await update.effective_message.reply_text("У вас нет доступа к этой команде.")
        return ConversationHandler.END

    await update.effective_message.reply_text(
        "Админ-панель. Выберите действие:", reply_markup=admin_menu_keyboard()
    )
    return ADMIN_SELECT_DATE


async def admin_menu_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор действия в админ-панели."""
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "admin_show_date":
        await query.message.reply_text("Введите дату в формате ДД.ММ.ГГГГ:")
        return ADMIN_SELECT_DATE
    if action == "admin_delete":
        await query.message.reply_text("Введите ID записи для удаления:")
        return ADMIN_DELETE_ID

    return ADMIN_SELECT_DATE


async def admin_show_by_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выводит все записи на указанную админом дату."""
    db = _get_db(context)
    settings = _get_settings(context)

    try:
        target_date = datetime.strptime(update.effective_message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await update.effective_message.reply_text(
            "Неверный формат даты. Используйте ДД.ММ.ГГГГ:"
        )
        return ADMIN_SELECT_DATE

    tz = now_moscow(settings.timezone).tzinfo
    start_dt = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=tz)
    end_dt = start_dt + timedelta(days=1)

    appointments = await db.get_appointments_by_date(start_dt, end_dt)
    if not appointments:
        await update.effective_message.reply_text("На выбранную дату записей нет.")
        return ADMIN_SELECT_DATE

    lines = [
        (
            f"ID {item.id} | user {item.user_id}\n"
            f"Услуга: {item.service}\n"
            f"Время: {format_datetime_ru(item.appointment_time)}\n"
            f"Статус: {item.status}"
        )
        for item in appointments
    ]
    await update.effective_message.reply_text("\n\n".join(lines))
    return ADMIN_SELECT_DATE


async def admin_delete_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Удаляет запись по ID (админ)."""
    db = _get_db(context)
    text = update.effective_message.text.strip()
    if not text.isdigit():
        await update.effective_message.reply_text("ID должен быть целым числом.")
        return ADMIN_DELETE_ID

    deleted = await db.delete_appointment(int(text))
    if deleted:
        await update.effective_message.reply_text("Запись удалена.")
    else:
        await update.effective_message.reply_text("Запись с таким ID не найдена.")
    return ADMIN_SELECT_DATE


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка неизвестных команд."""
    await update.effective_message.reply_text(
        "Неизвестная команда. Используйте /start для начала работы."
    )


async def unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка неизвестных callback-кнопок, чтобы не было бесконечной загрузки."""
    query = update.callback_query
    if not query:
        return
    await query.answer("Кнопка устарела. Откройте /start и попробуйте снова.", show_alert=False)
    logger.warning("Необработанный callback_data: %s", query.data)


def build_handlers() -> list:
    """Собирает все обработчики для регистрации в Application."""
    book_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(book_start, pattern="^menu_book$"),
            CommandHandler("book", book_start),
        ],
        states={
            BOOK_SELECT_SERVICE: [CallbackQueryHandler(book_select_service, pattern=r"^service::")],
            BOOK_SELECT_DATE: [
                CallbackQueryHandler(book_select_date, pattern=r"^(date::|calnav::|calnoop$)")
            ],
            BOOK_SELECT_TIME: [CallbackQueryHandler(book_select_time, pattern=r"^time::")],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_flow, pattern=r"^cancel_flow$"),
            CommandHandler("cancel", cancel_flow),
        ],
        name="booking_conversation",
        persistent=False,
    )

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_command)],
        states={
            ADMIN_SELECT_DATE: [
                CallbackQueryHandler(admin_menu_action, pattern=r"^admin_(show_date|delete)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_show_by_date),
            ],
            ADMIN_DELETE_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_delete_by_id),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_flow)],
        name="admin_conversation",
        persistent=False,
    )

    return [
        CommandHandler("start", start_command),
        CommandHandler("myid", my_id_command),
        CommandHandler("testadmin", test_admin_notify_command),
        CommandHandler("myappointments", my_appointments_command),
        CommandHandler("cancelappointment", cancel_appointment_command),
        CallbackQueryHandler(check_subscription_callback, pattern=r"^check_subscription$"),
        CallbackQueryHandler(show_main_menu, pattern=r"^go_main_menu$"),
        CallbackQueryHandler(my_appointments_callback, pattern=r"^menu_my_appointments$"),
        CallbackQueryHandler(cancel_appointment_callback, pattern=r"^cancel_appointment::"),
        book_conv,
        admin_conv,
        CallbackQueryHandler(unknown_callback),
        MessageHandler(filters.COMMAND, unknown_command),
    ]
