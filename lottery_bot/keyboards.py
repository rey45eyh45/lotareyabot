"""Reusable Telegram keyboards."""
from __future__ import annotations

from typing import Iterable, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard for regular users."""
    return ReplyKeyboardMarkup(
        keyboard=[
            ["🎟 Chiptani sotib olish", "📋 Mening chiptalarim"],
            ["ℹ️ O'yin haqida"],
        ],
        resize_keyboard=True,
    )


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard for admin actions."""
    return ReplyKeyboardMarkup(
        keyboard=[
            ["🏠 Bosh sahifa", "📊 Statistika"],
            ["⏳ Kutilayotgan to'lovlar", "✅ Tasdiqlangan to'lovlar"],
            ["✉️ Xabar yuborish", "👥 Foydalanuvchilar"],
            ["📡 Kanal boshqaruvi", "📥 Excel eksport"],
            ["⚙️ Bot sozlamlari"],
        ],
        resize_keyboard=True,
    )


def admin_decision_keyboard(purchase_id: str) -> InlineKeyboardMarkup:
    """Inline decision buttons for purchase moderation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve:{purchase_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject:{purchase_id}"),
            ]
        ]
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard with cancel button for purchase flow."""
    return ReplyKeyboardMarkup(
        keyboard=[["❌ Bekor qilish"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def request_contact_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard requesting the user's phone number."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📞 Telefon raqamni yuborish", request_contact=True)],
            ["❌ Bekor qilish"],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def subscription_prompt_keyboard(channels: Iterable[dict]) -> InlineKeyboardMarkup:
    """Inline keyboard showing subscription links and a re-check button."""
    buttons: List[List[InlineKeyboardButton]] = []
    for channel in channels:
        link = channel.get("link")
        title = channel.get("title") or channel.get("id") or "Kanal"
        if link:
            buttons.append([InlineKeyboardButton(title, url=link)])
    buttons.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_subscription")])
    return InlineKeyboardMarkup(buttons)
