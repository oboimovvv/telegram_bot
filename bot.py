"""Точка входа в проект Telegram-бота записи на услуги маникюра."""

from __future__ import annotations

import logging

from telegram.ext import Application, CallbackContext

from config import get_settings
from database import Database
from handlers import build_handlers


def setup_logging(log_file: str) -> None:
    """Настраивает логирование в консоль и файл."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


async def archive_past_appointments_job(context: CallbackContext) -> None:
    """
    Периодическая задача:
    переводит прошедшие активные записи в статус completed.
    """
    db: Database = context.application.bot_data["db"]
    settings = context.application.bot_data["settings"]
    tz_name = settings.timezone

    from utils import now_moscow  # Локальный импорт, чтобы избежать циклических зависимостей.

    updated = await db.mark_past_appointments_completed(now_moscow(tz_name))
    if updated:
        logging.getLogger(__name__).info("Архивировано записей в completed: %s", updated)


def build_application() -> Application:
    """Создаёт и настраивает Application со всеми обработчиками."""
    settings = get_settings()
    setup_logging(settings.log_file)

    db = Database(settings.database_url)

    # Увеличиваем HTTP-таймауты: это снижает вероятность падения при нестабильной сети.
    application = (
        Application.builder()
        .token(settings.bot_token)
        .concurrent_updates(False)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )
    application.bot_data["db"] = db
    application.bot_data["settings"] = settings

    for handler in build_handlers():
        application.add_handler(handler)

    # Настраиваем периодическую архивацию прошедших записей.
    if application.job_queue is not None:
        application.job_queue.run_repeating(
            archive_past_appointments_job,
            interval=1800,
            first=10,
            name="archive_past_appointments",
        )
    else:
        logging.getLogger(__name__).warning(
            "JobQueue недоступен. Установите APScheduler для фоновых задач."
        )

    async def _post_init(app: Application) -> None:
        """Создаёт таблицы перед началом polling."""
        await db.create_tables()
        logging.getLogger(__name__).info("База данных инициализирована.")

    application.post_init = _post_init
    return application


if __name__ == "__main__":
    app = build_application()
    settings = app.bot_data["settings"]
    if settings.run_mode == "webhook":
        logging.getLogger(__name__).info(
            "Запуск в webhook-режиме: %s%s", settings.webhook_url, settings.webhook_path
        )
        app.run_webhook(
            listen=settings.webapp_host,
            port=settings.webapp_port,
            url_path=settings.webhook_path.lstrip("/"),
            webhook_url=f"{settings.webhook_url.rstrip('/')}{settings.webhook_path}",
            drop_pending_updates=True,
        )
    else:
        logging.getLogger(__name__).info("Запуск в polling-режиме.")
        app.run_polling(drop_pending_updates=True)
