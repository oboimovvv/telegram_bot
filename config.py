"""Конфигурация приложения, загружаемая из .env."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    """Структура настроек проекта."""

    bot_token: str
    channel_id: str
    admin_id: int
    database_url: str
    timezone: str
    log_file: str
    run_mode: str
    webhook_url: str
    webhook_path: str
    webapp_host: str
    webapp_port: int


def get_settings() -> Settings:
    """
    Загружает настройки из файла .env.

    Ошибка поднимается сразу, если не указаны критичные параметры.
    """
    load_dotenv()

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    channel_id = os.getenv("CHANNEL_ID", "@your_nail_channel").strip()
    admin_id_raw = os.getenv("ADMIN_ID", "").strip()
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///nail_bot.db").strip()
    timezone = os.getenv("TIMEZONE", "Europe/Moscow").strip()
    log_file = os.getenv("LOG_FILE", "bot.log").strip()
    run_mode = os.getenv("RUN_MODE", "polling").strip().lower()
    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    webhook_path = os.getenv("WEBHOOK_PATH", "/telegram-webhook").strip() or "/telegram-webhook"
    webapp_host = os.getenv("WEBAPP_HOST", "0.0.0.0").strip()
    webapp_port_raw = os.getenv("PORT", os.getenv("WEBAPP_PORT", "10000")).strip()

    if not bot_token:
        raise ValueError("Не задан BOT_TOKEN в .env")
    if not admin_id_raw:
        raise ValueError("Не задан ADMIN_ID в .env")

    try:
        admin_id = int(admin_id_raw)
    except ValueError as exc:
        raise ValueError("ADMIN_ID должен быть целым числом.") from exc
    try:
        webapp_port = int(webapp_port_raw)
    except ValueError as exc:
        raise ValueError("PORT/WEBAPP_PORT должен быть целым числом.") from exc

    if run_mode not in {"polling", "webhook"}:
        raise ValueError("RUN_MODE должен быть polling или webhook.")
    if run_mode == "webhook" and not webhook_url:
        raise ValueError("Для RUN_MODE=webhook нужно указать WEBHOOK_URL.")

    return Settings(
        bot_token=bot_token,
        channel_id=channel_id,
        admin_id=admin_id,
        database_url=database_url,
        timezone=timezone,
        log_file=log_file,
        run_mode=run_mode,
        webhook_url=webhook_url,
        webhook_path=webhook_path,
        webapp_host=webapp_host,
        webapp_port=webapp_port,
    )
