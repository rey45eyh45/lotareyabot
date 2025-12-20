"""Entry point for the lottery Telegram bot."""
from __future__ import annotations

from pathlib import Path

from telegram.ext import Application

from lottery_bot.config import get_settings
from lottery_bot.handlers import register_handlers
from lottery_bot.storage import StorageManager


def main() -> None:
    settings = get_settings()
    storage = StorageManager(
        Path("data/store.json"), total_tickets=settings.total_tickets, default_card_number=settings.card_number
    )

    application = Application.builder().token(settings.bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["storage"] = storage

    register_handlers(application)

    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
