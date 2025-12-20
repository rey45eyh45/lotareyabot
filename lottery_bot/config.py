"""Application configuration helpers."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(dotenv_path=Path(".env"))


@dataclass(frozen=True)
class Settings:
    """Strongly-typed configuration values."""

    bot_token: str
    admin_id: int
    card_number: str
    prize_name: str
    ticket_price: int = 50_000
    total_tickets: int = 300


def _require_env(name: str) -> str:
    """Read an environment variable or raise a helpful error."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is required.")
    return value


def get_settings() -> Settings:
    """Hydrate settings from environment variables."""
    token = _require_env("BOT_TOKEN")
    admin_raw = _require_env("ADMIN_ID")
    card_number = _require_env("CARD_NUMBER")
    prize_name = os.getenv("PRIZE_NAME", "iPhone 16 Pro Max")

    try:
        admin_id = int(admin_raw)
    except ValueError as exc:  # pragma: no cover - defensive branch
        raise RuntimeError("ADMIN_ID must be an integer.") from exc

    ticket_price = int(os.getenv("TICKET_PRICE", "50000"))
    total_tickets = int(os.getenv("TOTAL_TICKETS", "300"))

    return Settings(
        bot_token=token,
        admin_id=admin_id,
        card_number=card_number,
        prize_name=prize_name,
        ticket_price=ticket_price,
        total_tickets=total_tickets,
    )
