"""Handlers dedicated to administrator actions."""
from __future__ import annotations

import asyncio
import os
import sys
import shutil
import tempfile
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from lottery_bot.keyboards import admin_menu_keyboard
from lottery_bot.storage import StorageManager


def register_admin_handlers(application) -> None:
    """Register admin command, message, and callback handlers."""
    settings = application.bot_data["settings"]
    admin_filter = filters.User(user_id=[settings.admin_id])

    admin_cancel_handler = CommandHandler("cancel", admin_cancel, filters=admin_filter)
    application.add_handler(admin_cancel_handler, group=-1)
    application.add_handler(CommandHandler("admin", admin_home, filters=admin_filter))
    application.add_handler(
        MessageHandler(admin_filter & filters.Regex("Xabar yuborish"), admin_broadcast_entry)
    )
    application.add_handler(MessageHandler(admin_filter & filters.Regex("Statistika"), admin_stats))
    application.add_handler(
        MessageHandler(admin_filter & filters.Regex("Tasdiqlanganlarni bekor qilish"), admin_list_approved)
    )
    application.add_handler(
        MessageHandler(admin_filter & filters.Regex("Bot sozlamlari"), admin_settings_entry)
    )
    application.add_handler(
        MessageHandler(admin_filter & filters.Regex("Kanal boshqaruvi"), admin_subscription_entry)
    )
    application.add_handler(
        MessageHandler(admin_filter & filters.Regex("Excel eksport"), admin_export_excel)
    )
    application.add_handler(CallbackQueryHandler(admin_decision, pattern=r"^(approve|reject):"))
    application.add_handler(CallbackQueryHandler(admin_subscription_toggle, pattern="^subscription:toggle$"))
    application.add_handler(CallbackQueryHandler(admin_subscription_refresh, pattern="^subscription:refresh$"))
    application.add_handler(CallbackQueryHandler(admin_subscription_close, pattern="^subscription:close$"))
    application.add_handler(CallbackQueryHandler(admin_subscription_list, pattern="^subscription:list$"))
    application.add_handler(CallbackQueryHandler(admin_subscription_add, pattern="^subscription:add$"))
    application.add_handler(
        CallbackQueryHandler(admin_subscription_prompt_remove, pattern="^subscription:prompt_remove$")
    )
    application.add_handler(CallbackQueryHandler(admin_subscription_remove, pattern=r"^subscription:remove:"))
    application.add_handler(CallbackQueryHandler(admin_subscription_cancel_input, pattern="^subscription:cancel_input$"))
    application.add_handler(CallbackQueryHandler(admin_subscription_no_channels, pattern="^subscription:no_channels$"))
    application.add_handler(
        CallbackQueryHandler(admin_subscription_edit_message, pattern="^subscription:edit_message$")
    )
    application.add_handler(CallbackQueryHandler(admin_cancel_approved, pattern=r"^approved:cancel:"))
    application.add_handler(CallbackQueryHandler(admin_approved_close, pattern="^approved:close$"))
    application.add_handler(CallbackQueryHandler(admin_settings_restart, pattern="^settings:restart$"))
    application.add_handler(CallbackQueryHandler(admin_settings_backup, pattern="^settings:backup$"))
    application.add_handler(CallbackQueryHandler(admin_settings_change_card, pattern="^settings:change_card$"))
    application.add_handler(CallbackQueryHandler(admin_settings_change_manager, pattern="^settings:change_manager$"))
    application.add_handler(CallbackQueryHandler(admin_settings_cancel_input, pattern="^settings:cancel_input$"))
    application.add_handler(CallbackQueryHandler(admin_start_message_entry_cb, pattern="^settings:start_edit$"))
    application.add_handler(CallbackQueryHandler(admin_start_message_cancel, pattern="^cancel_start_message$"))
    application.add_handler(CallbackQueryHandler(admin_game_info_message_entry_cb, pattern="^settings:game_info_edit$"))
    application.add_handler(CallbackQueryHandler(admin_game_info_message_cancel, pattern="^cancel_game_info_message$"))
    application.add_handler(CallbackQueryHandler(admin_game_info_message_reset, pattern="^reset_game_info_message$"))
    application.add_handler(CallbackQueryHandler(admin_broadcast_cancel, pattern="^cancel_broadcast$"))
    application.add_handler(CallbackQueryHandler(admin_settings_close, pattern="^settings:close$"))
    subscription_input_handler = MessageHandler(admin_filter & ~filters.COMMAND, admin_subscription_text_input)
    subscription_input_handler.block = False
    application.add_handler(subscription_input_handler, group=5)

    settings_input_handler = MessageHandler(admin_filter & ~filters.COMMAND, admin_settings_text_input)
    settings_input_handler.block = False
    application.add_handler(settings_input_handler, group=6)

    mode_router_handler = MessageHandler(admin_filter & ~filters.COMMAND, admin_active_mode_router)
    mode_router_handler.block = False
    application.add_handler(mode_router_handler, group=7)


def _format_money(value: int | float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _format_decimal(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_money_decimal(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", " ")
    return formatted.rstrip("0").rstrip(".")


def _settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Botni qayta ishga tushirish", callback_data="settings:restart")],
            [InlineKeyboardButton("💾 Bazani backup qilish", callback_data="settings:backup")],
            [InlineKeyboardButton("💳 Karta raqamini almashtirish", callback_data="settings:change_card")],
            [InlineKeyboardButton("👤 Menejer kontaktini almashtirish", callback_data="settings:change_manager")],
            [InlineKeyboardButton("✏️ Start xabarini tahrirlash", callback_data="settings:start_edit")],
            [InlineKeyboardButton("ℹ️ O'yin haqida xabarini tahrirlash", callback_data="settings:game_info_edit")],
            [InlineKeyboardButton("❌ Yopish", callback_data="settings:close")],
        ]
    )


def _subscription_management_keyboard(enabled: bool, has_channels: bool) -> InlineKeyboardMarkup:
    toggle_text = "✅ Obunani o'chirish" if enabled else "✅ Obunani yoqish"
    buttons = [
        [InlineKeyboardButton(toggle_text, callback_data="subscription:toggle"),
            InlineKeyboardButton("📋 Kanallar ro'yxati", callback_data="subscription:list"),
        ],
        [
            InlineKeyboardButton("➕ Kanal qo'shish", callback_data="subscription:add"),
            InlineKeyboardButton("🗑 Kanal o'chirish", callback_data="subscription:prompt_remove"),
        ],
        [InlineKeyboardButton("✏️ Obuna xabarini tahrirlash", callback_data="subscription:edit_message"), InlineKeyboardButton("❌ Yopish", callback_data="subscription:close")],
    ]
    if not has_channels:
        buttons[2][1] = InlineKeyboardButton("🗑 Kanal o'chirish", callback_data="subscription:no_channels")
    return InlineKeyboardMarkup(buttons)


def _format_channel_list(channels) -> str:
    if not channels:
        return "• Hali kanal qo'shilmagan."
    lines = []
    for idx, channel in enumerate(channels, start=1):
        title = channel.get("title") or channel.get("id") or "Kanal"
        link = channel.get("link")
        if link:
            lines.append(f"{idx}. {title} — {link}")
        else:
            lines.append(f"{idx}. {title}")
    return "\n".join(lines)


def _build_subscription_summary(config, notice: Optional[str] = None) -> tuple[str, InlineKeyboardMarkup]:
    status = "Yoqilgan ✅" if config.get("enabled") else "O'chirilgan ❌"
    channels = config.get("channels", [])
    lines = [
        "📺 Kanal boshqaruvi",
        f"🔐 Majburiy obuna: {status}",
        f"📡 Kanallar soni: {len(channels)}",
        "",
        "Amalni tanlang:",
        "",
        "📡 Kuzatuvdagi kanallar:",
        _format_channel_list(channels),
    ]
    if notice:
        lines.extend(["", notice])
    keyboard = _subscription_management_keyboard(config.get("enabled", False), bool(config.get("channels")))
    return "\n".join(lines), keyboard


def _set_subscription_message_ref(context: CallbackContext, chat_id: int, message_id: int) -> None:
    context.user_data["subscription_message_ref"] = (chat_id, message_id)


def _build_approved_summary(approved) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    if not approved:
        return (
            "✅ Hozircha bekor qilish uchun tasdiqlangan to'lovlar yo'q.",
            None,
        )

    lines = ["✅ Tasdiqlangan to'lovlar (bekor qilish mumkin):"]
    buttons = []
    for item in approved:
        pid = item.get("purchase_id")
        user_display = item.get("full_name") or f"ID {item.get('user_id')}"
        tickets = item.get("tickets", [])
        amount = _format_money(item.get("amount", 0))
        lines.append(
            f"• {pid} | {user_display} | 🎟 {len(tickets)} ta | 💰 {amount} so'm"
        )
        buttons.append(
            [InlineKeyboardButton(f"↩️ Bekor qilish — {pid}", callback_data=f"approved:cancel:{pid}")]
        )

    buttons.append([InlineKeyboardButton("❌ Yopish", callback_data="approved:close")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _refresh_subscription_message_from_ref(
    context: CallbackContext,
    *,
    notice: Optional[str] = None,
) -> None:
    ref = context.user_data.get("subscription_message_ref")
    if not ref:
        return
    chat_id, message_id = ref
    storage: StorageManager = context.application.bot_data["storage"]
    config = await storage.get_subscription_config()
    summary, keyboard = _build_subscription_summary(config, notice=notice)
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=summary,
            reply_markup=keyboard,
        )
    except TelegramError:
        pass


async def admin_home(update: Update, context: CallbackContext) -> None:
    """Show the admin navigation menu."""
    await update.message.reply_text("👋 Admin paneliga xush kelibsiz!", reply_markup=admin_menu_keyboard())


async def admin_stats(update: Update, context: CallbackContext) -> None:
    """Deliver detailed analytics for the admin."""
    storage: StorageManager = context.application.bot_data["storage"]
    stats = await storage.get_detailed_stats()

    summary_lines = [
        "📊 Umumiy statistika",
        "",
        "👥 Foydalanuvchilar:",
        f"• Jami: {stats['total_users']}",
        f"• 24 soat ichida faol: {stats['active_users_24h']}",
        f"• 24 soat ichida yangi: {stats['new_users_24h']}",
        "",
        "🎟 Chiptalar:",
        f"• Sotilgan: {stats['tickets_sold']} / {stats['total_tickets']}",
        f"• Qolgan: {stats['remaining_tickets']}",
        f"• O'rtacha chipta / foydalanuvchi: {_format_decimal(stats['avg_tickets_per_user'])}",
        "",
        "💰 To'lovlar:",
        f"• Jami daromad: {_format_money(stats['total_revenue'])} so'm",
        f"• Jami to'lovlar soni: {stats['total_purchases']}",
        f"• O'rtacha to'lov / foydalanuvchi: {_format_money_decimal(stats['avg_spend_per_user'])} so'm",
        f"• Tasdiqlangan: {stats['approved_count']} | Rad etilgan: {stats['rejected_count']}",
        f"• Kutilayotgan: {stats['pending_count']} (≈ {_format_money(stats['pending_amount'])} so'm)",
    ]

    if stats["top_users"]:
        summary_lines.append("")
        summary_lines.append("🏆 Eng faol qatnashchilar:")
        for idx, entry in enumerate(stats["top_users"], start=1):
            display_name = entry.get("full_name") or f"ID {entry['user_id']}"
            if entry.get("username"):
                display_name += f" (@{entry['username']})"
            summary_lines.append(
                f"{idx}. {display_name} — {entry['tickets']} ta chipta, {_format_money(entry['spent'])} so'm"
            )

    await update.message.reply_text("\n".join(summary_lines), reply_markup=admin_menu_keyboard())

async def admin_list_approved(update: Update, context: CallbackContext) -> None:
    """List approved purchases with an option to cancel them."""
    storage: StorageManager = context.application.bot_data["storage"]
    approved = await storage.list_approved()
    text, markup = _build_approved_summary(approved)
    await update.message.reply_text(text, reply_markup=markup or admin_menu_keyboard())


async def admin_subscription_entry(update: Update, context: CallbackContext) -> None:
    """Open the subscription management popup."""
    storage: StorageManager = context.application.bot_data["storage"]
    config = await storage.get_subscription_config()
    summary, keyboard = _build_subscription_summary(config)
    sent = await update.message.reply_text(summary, reply_markup=keyboard)
    _set_subscription_message_ref(context, sent.chat_id, sent.message_id)


async def admin_settings_entry(update: Update, context: CallbackContext) -> None:
    """Show bot settings actions."""
    storage: StorageManager = context.application.bot_data["storage"]
    card_number = await storage.get_card_number()
    manager_contact = await storage.get_manager_contact()
    text = (
        "⚙️ Bot sozlamlari\n"
        f"• Joriy karta: {card_number or 'kiritilmagan'}\n"
        f"• Menejer: {manager_contact or 'belgilangan emas'}\n"
        "• Backup va restartni shu yerda boshqarishingiz mumkin."
    )
    await update.message.reply_text(text, reply_markup=_settings_keyboard())


async def _edit_subscription_menu(query, context: CallbackContext, notice: Optional[str] = None) -> None:
    storage: StorageManager = context.application.bot_data["storage"]
    config = await storage.get_subscription_config()
    summary, keyboard = _build_subscription_summary(config, notice=notice)
    try:
        await query.edit_message_text(summary, reply_markup=keyboard)
    except TelegramError:
        pass
    else:
        if query.message:
            _set_subscription_message_ref(context, query.message.chat_id, query.message.message_id)


async def admin_subscription_refresh(update: Update, context: CallbackContext) -> None:
    """Refresh the subscription overview from inline button."""
    query = update.callback_query
    await query.answer()
    await _edit_subscription_menu(query, context)


async def admin_settings_close(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_text("⚙️ Sozlamalar yopildi.")
    except TelegramError:
        pass


async def admin_settings_restart(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer("Bot qayta ishga tushirilmoqda...", show_alert=True)
    await query.edit_message_text("🔄 Bot qayta ishga tushirilmoqda...")
    # Restart current process.
    os.execl(sys.executable, sys.executable, *sys.argv)


async def admin_settings_backup(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    storage: StorageManager = context.application.bot_data["storage"]
    src_path = getattr(storage, "_path", None)
    if not src_path or not os.path.exists(src_path):
        await query.answer("Backup uchun fayl topilmadi.", show_alert=True)
        return

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    try:
        shutil.copy(src_path, temp_file.name)
        temp_file.close()
        with open(temp_file.name, "rb") as handle:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=handle,
                filename="store_backup.json",
                caption="💾 Baza backup fayli.",
            )
    finally:
        try:
            os.remove(temp_file.name)
        except OSError:
            pass


async def admin_settings_change_card(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data["settings_mode"] = "card_number"
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "💳 Yangi karta raqamini yuboring.\n"
            "Misol: 9860 1234 5678 9012\n"
            "Bekor qilish uchun tugmadan foydalaning."
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Bekor qilish", callback_data="settings:cancel_input")]]
        ),
    )


async def admin_settings_change_manager(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data["settings_mode"] = "manager_contact"
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "👤 Yangi menejer username ni yuboring.\n"
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Bekor qilish", callback_data="settings:cancel_input")]]
        ),
    )


async def admin_subscription_toggle(update: Update, context: CallbackContext) -> None:
    """Toggle mandatory subscription state."""
    query = update.callback_query
    storage: StorageManager = context.application.bot_data["storage"]
    config = await storage.get_subscription_config()
    new_state = not config.get("enabled", False)
    await storage.set_subscription_enabled(new_state)
    await _edit_subscription_menu(query, context, notice="✅ Holat yangilandi.")
    status_text = "Majburiy obuna yoqildi." if new_state else "Majburiy obuna o'chirildi."
    await query.answer(status_text, show_alert=True)


async def admin_subscription_close(update: Update, context: CallbackContext) -> None:
    """Close the subscription popup."""
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_text("📡 Kanal boshqaruvi yopildi.")
    except TelegramError:
        pass


async def admin_subscription_add(update: Update, context: CallbackContext) -> None:
    """Prepare to add a new subscription channel."""
    query = update.callback_query
    await query.answer()
    context.user_data["subscription_mode"] = "add"
    if query.message:
        _set_subscription_message_ref(context, query.message.chat_id, query.message.message_id)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "➕ Kanal qo'shish uchun kanal username yoki havolasini yuboring, yoki kanaldan xabarni "
            "forward qiling. Bekor qilish uchun tugmadan foydalaning."
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Bekor qilish", callback_data="subscription:cancel_input")]]
        ),
    )


async def admin_subscription_prompt_remove(update: Update, context: CallbackContext) -> None:
    """Show removable channels."""
    query = update.callback_query
    await query.answer()
    storage: StorageManager = context.application.bot_data["storage"]
    config = await storage.get_subscription_config()
    channels = config.get("channels", [])
    if not channels:
        await query.answer("Kanal qo'shilmagan.", show_alert=True)
        return

    buttons = [
        [
            InlineKeyboardButton(
                f"❌ {channel.get('title') or channel.get('id')}", callback_data=f"subscription:remove:{channel.get('id')}"
            )
        ]
        for channel in channels
    ]
    buttons.append([InlineKeyboardButton("⬅️ Ortga", callback_data="subscription:refresh")])
    try:
        await query.edit_message_text(
            "❌ O'chirish uchun kanalni tanlang:", reply_markup=InlineKeyboardMarkup(buttons)
        )
    except TelegramError:
        pass


async def admin_subscription_cancel_input(update: Update, context: CallbackContext) -> None:
    """Cancel the current subscription input (add/edit) and return to menu."""
    query = update.callback_query
    await query.answer("Bekor qilindi", show_alert=True)
    context.user_data.pop("subscription_mode", None)
    await _edit_subscription_menu(query, context, notice="❌ Jarayon bekor qilindi.")


async def admin_subscription_remove(update: Update, context: CallbackContext) -> None:
    """Remove a selected subscription channel."""
    query = update.callback_query
    parts = query.data.split(":", maxsplit=2)
    channel_id = parts[2] if len(parts) > 2 else ""
    storage: StorageManager = context.application.bot_data["storage"]
    removed = await storage.remove_subscription_channel(channel_id)
    notice = "✅ Kanal o'chirildi." if removed else "ℹ️ Kanal topilmadi."
    await _edit_subscription_menu(query, context, notice=notice)
    await query.answer(notice, show_alert=True)


async def admin_subscription_edit_message(update: Update, context: CallbackContext) -> None:
    """Prompt admin to edit subscription reminder text."""
    query = update.callback_query
    await query.answer()
    context.user_data["subscription_mode"] = "edit_message"
    if query.message:
        _set_subscription_message_ref(context, query.message.chat_id, query.message.message_id)
    current = await context.application.bot_data["storage"].get_subscription_message()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "📝 Yangi majburiy obuna xabarini yuboring. Matnda {channels} o'zgaruvchisi bo'lishi kerak.\n"
            "Bekor qilish uchun /cancel yuboring.\n"
            "\nJoriy xabar:\n" + current
        ),
    )


async def _resolve_channel(update: Update, context: CallbackContext) -> Optional[dict]:
    """Extract channel information from the admin's message."""
    message = update.message
    chat = message.forward_from_chat
    if chat is None:
        text = (message.text or "").strip()
        if not text:
            await message.reply_text("❗ Kanal username yoki havolasini yuboring.")
            return None
        identifier = text.split()[0]
        if "t.me/" in identifier:
            identifier = identifier.split("t.me/")[-1]
        identifier = identifier.strip()
        if identifier.startswith("https://") or identifier.startswith("http://"):
            identifier = identifier.split("/")[-1]
        if not identifier.startswith("@") and not identifier.startswith("-100"):
            identifier = f"@{identifier}" if not identifier.startswith("+") else identifier
        try:
            chat = await context.bot.get_chat(identifier)
        except TelegramError:
            await message.reply_text("❗ Kanal topilmadi. Username yoki havolasini tekshiring.")
            return None

    if chat.type not in ("channel", "supergroup"):
        await message.reply_text("❗ Faqat kanal yoki supergruppani yuboring.")
        return None

    channel_id = str(chat.id)
    title = chat.title or getattr(chat, "full_name", None) or chat.username or channel_id
    username = getattr(chat, "username", None)
    link = None
    if username:
        link = f"https://t.me/{username}"
    elif getattr(chat, "invite_link", None):
        link = chat.invite_link

    return {"channel_id": channel_id, "title": title, "link": link}


async def admin_subscription_text_input(update: Update, context: CallbackContext) -> None:
    """Handle follow-up text for subscription management actions."""
    mode = context.user_data.get("subscription_mode")
    if not mode:
        return

    storage: StorageManager = context.application.bot_data["storage"]

    if mode == "add":
        channel = await _resolve_channel(update, context)
        if not channel:
            return
        await storage.add_subscription_channel(channel["channel_id"], channel["title"], channel.get("link"))
        context.user_data.pop("subscription_mode", None)
        await update.message.reply_text(
            "✅ Kanal qo'shildi. Iltimos, botni ushbu kanalga administrator sifatida qo'shganingizga ishonch hosil qiling.",
        )
        await _refresh_subscription_message_from_ref(context, notice="✅ Kanal qo'shildi.")
    elif mode == "edit_message":
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text("❗ Matn bo'sh bo'lishi mumkin emas. Qayta yuboring.")
            return
        try:
            await storage.set_subscription_message(text)
        except ValueError as exc:
            await update.message.reply_text(f"❗ {exc}")
            return
        context.user_data.pop("subscription_mode", None)
        await update.message.reply_text("✅ Majburiy obuna xabari yangilandi.")
        await _refresh_subscription_message_from_ref(context, notice="✅ Xabar yangilandi.")


async def admin_settings_text_input(update: Update, context: CallbackContext) -> None:
    """Handle text inputs for settings flows (e.g., card number)."""
    mode = context.user_data.get("settings_mode")
    if not mode:
        return

    if mode == "card_number":
        card = (update.message.text or "").strip()
        if not card:
            await update.message.reply_text("❗ Karta raqami bo'sh bo'lmasligi kerak.")
            return
        storage: StorageManager = context.application.bot_data["storage"]
        await storage.set_card_number(card)
        context.user_data.pop("settings_mode", None)
        await update.message.reply_text(
            f"✅ Karta raqami yangilandi: {card}", reply_markup=admin_menu_keyboard()
        )
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="⚙️ Bot sozlamalari yangilandi.",
            reply_markup=_settings_keyboard(),
        )
    elif mode == "manager_contact":
        contact = (update.message.text or "").strip()
        if not contact:
            await update.message.reply_text("❗ Username bo'sh bo'lmasligi kerak.")
            return
        if not contact.startswith("@"):  # normalize
            contact = "@" + contact
        storage: StorageManager = context.application.bot_data["storage"]
        await storage.set_manager_contact(contact)
        context.user_data.pop("settings_mode", None)
        await update.message.reply_text(
            f"✅ Menejer kontakti yangilandi: {contact}", reply_markup=admin_menu_keyboard()
        )
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="⚙️ Bot sozlamalari yangilandi.",
            reply_markup=_settings_keyboard(),
        )


async def admin_settings_cancel_input(update: Update, context: CallbackContext) -> None:
    """Cancel current settings input (card/manager)."""
    query = update.callback_query
    await query.answer("Bekor qilindi", show_alert=True)
    context.user_data.pop("settings_mode", None)
    try:
        await query.edit_message_text("⚙️ Amal bekor qilindi.")
    except TelegramError:
        pass


async def admin_subscription_list(update: Update, context: CallbackContext) -> None:
    """Send the current channel list in chat."""
    query = update.callback_query
    storage: StorageManager = context.application.bot_data["storage"]
    config = await storage.get_subscription_config()
    channels = config.get("channels", [])
    if not channels:
        await query.answer("Hali kanal qo'shilmagan.", show_alert=True)
        return

    text_lines = ["📋 Kanallar ro'yxati:"]
    for idx, channel in enumerate(channels, start=1):
        title = channel.get("title") or channel.get("id") or "Kanal"
        link = channel.get("link")
        if link:
            text_lines.append(f"{idx}. {title} — {link}")
        else:
            text_lines.append(f"{idx}. {title}")

    await query.answer("Kanallar ro'yxati yuborildi.")
    await context.bot.send_message(chat_id=query.message.chat_id, text="\n".join(text_lines))


async def admin_subscription_no_channels(update: Update, context: CallbackContext) -> None:
    """Inform admin that there are no channels to remove."""
    query = update.callback_query
    await query.answer("Hali kanal qo'shilmagan.", show_alert=True)


async def admin_approved_close(update: Update, context: CallbackContext) -> None:
    """Close the approved-list message."""
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_text("✅ Tasdiqlangan to'lovlar ro'yxati yopildi.")
    except TelegramError:
        pass


async def admin_cancel_approved(update: Update, context: CallbackContext) -> None:
    """Cancel an approved purchase and refund tickets."""
    query = update.callback_query
    parts = query.data.split(":", maxsplit=2)
    purchase_id = parts[2] if len(parts) > 2 else ""
    storage: StorageManager = context.application.bot_data["storage"]
    purchase = await storage.cancel_approved_purchase(purchase_id)
    if not purchase:
        await query.answer("Topilmadi yoki allaqachon bekor qilingan.", show_alert=True)
        return

    tickets = purchase.get("tickets", [])
    amount = _format_money(purchase.get("amount", 0))
    ticket_list = ", ".join(str(t) for t in sorted(tickets)) if tickets else "-"

    await query.answer("Bekor qilindi", show_alert=True)

    refreshed = await storage.list_approved()
    text, markup = _build_approved_summary(refreshed)
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except TelegramError:
        pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "↩️ Tasdiqlangan chek bekor qilindi.\n"
            f"Chek: {purchase_id}\n"
            f"Foydalanuvchi: {purchase.get('full_name') or purchase.get('user_id')}\n"
            f"🎟 Chiptalar: {ticket_list}\n"
            f"💰 To'lov: {amount} so'm"
        ),
        reply_markup=admin_menu_keyboard(),
    )

    # Notify user about cancellation if possible.
    user_id = purchase.get("user_id")
    if user_id:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "❗️ Sizning tasdiqlangan chiptangiz bekor qilindi.\n"
                    f"Chek ID: {purchase_id}\n"
                    f"🎟 Chiptalar: {ticket_list}\n"
                    "Savol bo'lsa, administrator bilan bog'laning."
                ),
            )
        except TelegramError:
            pass


async def admin_export_excel(update: Update, context: CallbackContext) -> None:
    """Generate and send an Excel report of approved purchases."""
    storage: StorageManager = context.application.bot_data["storage"]
    rows = await storage.get_ticket_export_rows()
    if not rows:
        await update.message.reply_text(
            "📭 Hozircha eksport qilish uchun tasdiqlangan to'lovlar yo'q.",
            reply_markup=admin_menu_keyboard(),
        )
        return

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Chiptalar"
    headers = [
        "Purchase ID",
        "Foydalanuvchi",
        "Username",
        "Telefon",
        "Chipta soni",
        "Chipta raqamlari",
        "To'lov (so'm)",
        "Tasdiqlangan vaqt",
    ]
    sheet.append(headers)

    header_font = Font(bold=True)
    header_align = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 22
    for col_idx, _ in enumerate(headers, start=1):
        cell = sheet.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.alignment = header_align

    # Wider, clearer columns
    widths = [18, 22, 18, 16, 14, 28, 16, 26]
    for idx, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(idx)].width = width

    for row in rows:
        tickets = ", ".join(str(ticket) for ticket in sorted(row.get("tickets", [])))
        sheet.append(
            [
                row.get("purchase_id"),
                row.get("full_name"),
                ("@" + row["username"]) if row.get("username") else "",
                row.get("phone_number") or "",
                row.get("quantity", 0),
                tickets,
                row.get("amount", 0),
                row.get("resolved_at") or "",
            ]
        )

    # Align text for readability
    center_cols = {1, 5, 7, 8}
    for row_idx, row in enumerate(sheet.iter_rows(min_row=2, max_row=sheet.max_row), start=2):
        for col_idx, cell in enumerate(row, start=1):
            if col_idx in center_cols:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(vertical="center")

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    try:
        workbook.save(temp_file.name)
        temp_file.close()
        with open(temp_file.name, "rb") as handle:
            await update.message.reply_document(
                document=handle,
                filename="lottery_export.xlsx",
                caption="📥 Tasdiqlangan chiptalar bo'yicha hisobot tayyor.",
            )
    finally:
        try:
            os.remove(temp_file.name)
        except OSError:
            pass

async def admin_decision(update: Update, context: CallbackContext) -> None:
    """Handle approval or rejection callbacks."""
    query = update.callback_query
    await query.answer()

    settings = context.application.bot_data["settings"]
    if query.from_user.id != settings.admin_id:
        await query.answer(text="Bu tugma faqat admin uchun.", show_alert=True)
        return

    action, purchase_id = query.data.split(":", maxsplit=1)
    storage: StorageManager = context.application.bot_data["storage"]

    if not await storage.is_pending(purchase_id):
        await _edit_admin_message(query, "ℹ️ Bu chek allaqachon ko'rib chiqilgan.")
        return

    if action == "approve":
        tickets, purchase = await storage.approve_purchase(purchase_id)
        if not tickets:
            await query.answer(text="Yetarli chipta qolmadi yoki purchase topilmadi.", show_alert=True)
            return

        ticket_list = ", ".join(str(t) for t in sorted(tickets))
        amount = _format_money(purchase.get("amount", 0))

        await _edit_admin_message(
            query,
            f"✅ Tasdiqlandi\n🎟 Chiptalar: {ticket_list}\n💰 To'lov: {amount} so'm",
        )

        await context.bot.send_message(
            chat_id=purchase["user_id"],
            text=(
                "🎉 Tabriklaymiz! To'lovingiz muvaffaqiyatli tasdiqlandi.\n"
                f"🎟 Sizga biriktirilgan chiptalar: {ticket_list}\n"
                "🙏 Ishtirokingiz uchun rahmat, omad yor bo'lsin!"
            ),
        )

        await context.bot.send_message(
            chat_id=settings.admin_id,
            text=f"✅ Tasdiqlandi: {purchase['full_name']} — {ticket_list} (💰 {amount} so'm)",
        )
    else:
        purchase = await storage.reject_purchase(purchase_id)
        if not purchase:
            await _edit_admin_message(query, "ℹ️ Bu chek allaqachon ko'rib chiqilgan.")
            return

        await _edit_admin_message(query, "❌ Chek rad etildi.")
        manager_contact = await storage.get_manager_contact()
        contact_username = manager_contact.lstrip("@") or "menejer_1w"
        contact_url = f"https://t.me/{contact_username}"
        await context.bot.send_message(
            chat_id=purchase["user_id"],
            text=(
                "❌ Kechirasiz, to'lov tasdiqlanmadi.\n"
                "Iltimos, ma'lumotlarni tekshirib, qayta yuboring."
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("admin bilan bog'lanish", url=contact_url)]
                ]
            ),
        )


async def admin_broadcast_entry(update: Update, context: CallbackContext) -> None:
    """Prompt admin for broadcast content."""
    if context.user_data.get("broadcast_mode") == "awaiting_content":
        await update.message.reply_text("ℹ️ Hozirda yuboriladigan xabarni kutyapman. Iltimos, xabarni yuboring yoki bekor qiling.")
        return

    context.user_data["broadcast_mode"] = "awaiting_content"
    if update.message:
        context.user_data["broadcast_ignore_message_id"] = update.message.message_id
    await update.message.reply_text(
        (
            "✉️ Yuboriladigan xabarni yuboring. Matn, rasm yoki video (caption bilan) qo'llab-quvvatlanadi.\n"
            "Bekor qilish uchun tugmadan foydalaning."
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Bekor qilish", callback_data="cancel_broadcast")]]
        ),
    )


async def admin_broadcast_handle_content(update: Update, context: CallbackContext) -> None:
    """Send broadcast message to all known users when mode is active."""
    if context.user_data.get("broadcast_mode") != "awaiting_content":
        return

    ignore_id = context.user_data.pop("broadcast_ignore_message_id", None)
    if ignore_id and update.message and update.message.message_id == ignore_id:
        return

    message = update.message
    if message.photo:
        payload = {
            "type": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": (message.caption or "").strip(),
        }
    elif message.video:
        payload = {
            "type": "video",
            "file_id": message.video.file_id,
            "caption": (message.caption or "").strip(),
        }
    else:
        text = (message.text or "").strip()
        if not text:
            await update.message.reply_text("❗ Xabar bo'sh bo'lishi mumkin emas. Qaytadan yuboring.")
            return
        payload = {"type": "text", "text": text}

    storage: StorageManager = context.application.bot_data["storage"]
    user_ids = await storage.list_user_ids()
    if not user_ids:
        context.user_data.pop("broadcast_mode", None)
        await update.message.reply_text(
            "📭 Hozircha xabar yuboriladigan foydalanuvchi mavjud emas.",
            reply_markup=admin_menu_keyboard(),
        )
        return

    await update.message.reply_text(
        f"✉️ Xabar yuborilmoqda... (jami {len(user_ids)} foydalanuvchi)", reply_markup=admin_menu_keyboard()
    )

    delivered = 0
    failed = 0
    for user_id in user_ids:
        try:
            if payload["type"] == "text":
                await context.bot.send_message(chat_id=user_id, text=payload["text"])
            elif payload["type"] == "photo":
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=payload["file_id"],
                    caption=payload.get("caption") or None,
                )
            elif payload["type"] == "video":
                await context.bot.send_video(
                    chat_id=user_id,
                    video=payload["file_id"],
                    caption=payload.get("caption") or None,
                )
            delivered += 1
        except TelegramError:
            failed += 1
            continue
        await asyncio.sleep(0.05)

    context.user_data.pop("broadcast_mode", None)
    await update.message.reply_text(
        f"✅ Yuborildi: {delivered} ta\n⚠️ Yuborilmadi: {failed} ta",
        reply_markup=admin_menu_keyboard(),
    )


async def admin_broadcast_cancel(update: Update, context: CallbackContext) -> None:
    """Cancel the broadcast flow from inline button."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("broadcast_mode", None)
    context.user_data.pop("broadcast_ignore_message_id", None)
    await query.edit_message_text("✉️ Xabar yuborish bekor qilindi.")


async def admin_start_message_entry_cb(update: Update, context: CallbackContext) -> None:
    """Start-message edit flow triggered from settings inline button."""
    query = update.callback_query
    await query.answer()
    context.user_data["start_edit_mode"] = True
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "✏️ Start xabarining yangi matnini yoki media (caption bilan) yuboring.\n"
            "Bekor qilish uchun tugmadan foydalaning."
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Bekor qilish", callback_data="cancel_start_message")]]
        ),
    )


async def admin_start_message_handle_input(update: Update, context: CallbackContext) -> None:
    """Persist the new start message template when editing mode is active."""
    if not context.user_data.get("start_edit_mode"):
        return

    message = update.message
    if message.photo:
        text = (message.caption or "").strip()
        media = {"type": "photo", "file_id": message.photo[-1].file_id}
    elif message.video:
        text = (message.caption or "").strip()
        media = {"type": "video", "file_id": message.video.file_id}
    else:
        text = (message.text or "").strip()
        media = None

    if not text:
        await update.message.reply_text("❗ Matn bo'sh bo'lishi mumkin emas. Qayta kiriting.")
        return

    storage: StorageManager = context.application.bot_data["storage"]
    settings = context.application.bot_data["settings"]

    try:
        await storage.set_start_message(text=text, media=media)
    except ValueError as exc:
        await update.message.reply_text(f"❗ {exc}")
        return

    remaining = await storage.remaining_tickets()
    preview = await storage.render_start_content(
        prize=settings.prize_name,
        total_tickets=settings.total_tickets,
        remaining_tickets=remaining,
        ticket_price=_format_money(settings.ticket_price),
    )

    if preview.get("media") and preview["media"].get("type") == "photo":
        await update.message.reply_photo(
            photo=preview["media"]["file_id"],
            caption="✅ Start xabari yangilandi:\n\n" + preview["text"],
            reply_markup=admin_menu_keyboard(),
        )
    elif preview.get("media") and preview["media"].get("type") == "video":
        await update.message.reply_video(
            video=preview["media"]["file_id"],
            caption="✅ Start xabari yangilandi:\n\n" + preview["text"],
            reply_markup=admin_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "✅ Start xabari yangilandi. Joriy ko'rinish:\n\n" + preview["text"],
            reply_markup=admin_menu_keyboard(),
        )
    context.user_data.pop("start_edit_mode", None)


async def admin_start_message_cancel(update: Update, context: CallbackContext) -> None:
    """Cancel the start message editing flow via inline button."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("start_edit_mode", None)
    await query.edit_message_text("✏️ Start xabarini tahrirlash bekor qilindi.")


async def admin_game_info_message_entry_cb(update: Update, context: CallbackContext) -> None:
    """Begin game-info message editing from settings."""
    query = update.callback_query
    await query.answer()
    context.user_data["game_info_edit_mode"] = True
    storage: StorageManager = context.application.bot_data["storage"]
    current = await storage.get_game_info_message()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            "ℹ️ Yangi 'O'yin haqida' xabarini yuboring. Matnda quyidagi o'zgaruvchilardan foydalanishingiz mumkin:\n"
            "{prize}, {total_tickets}, {sold_tickets}, {remaining_tickets}, {ticket_price}.\n"
            "Standart holatga qaytarish yoki bekor qilish uchun pastdagi tugmalardan foydalaning.\n\n"
            "Joriy xabar:\n"
            f"{current}"
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("♻️ Standart holatga qaytarish", callback_data="reset_game_info_message")],
                [InlineKeyboardButton("Bekor qilish", callback_data="cancel_game_info_message")],
            ]
        ),
    )


async def admin_game_info_message_handle_input(update: Update, context: CallbackContext) -> None:
    """Persist the updated game-info message template."""
    if not context.user_data.get("game_info_edit_mode"):
        return

    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("❗ Faqat matn yuboring. Bo'sh xabar qabul qilinmaydi.")
        return

    storage: StorageManager = context.application.bot_data["storage"]
    settings = context.application.bot_data["settings"]

    try:
        await storage.set_game_info_message(text)
    except ValueError as exc:
        await update.message.reply_text(f"❗ {exc}")
        return

    preview = await storage.render_game_info_message(
        prize=settings.prize_name,
        total_tickets=settings.total_tickets,
        ticket_price=_format_money(settings.ticket_price),
    )

    await update.message.reply_text(
        "✅ 'O'yin haqida' xabari yangilandi. Joriy ko'rinish:\n\n" + preview,
        reply_markup=admin_menu_keyboard(),
    )
    context.user_data.pop("game_info_edit_mode", None)


async def admin_game_info_message_cancel(update: Update, context: CallbackContext) -> None:
    """Cancel game-info editing flow via inline button."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop("game_info_edit_mode", None)
    await query.edit_message_text("ℹ️ O'yin haqida xabarini tahrirlash bekor qilindi.")


async def admin_game_info_message_reset(update: Update, context: CallbackContext) -> None:
    """Restore the game-info message to its default template."""
    query = update.callback_query
    await query.answer()
    storage: StorageManager = context.application.bot_data["storage"]
    settings = context.application.bot_data["settings"]
    await storage.reset_game_info_message()
    preview = await storage.render_game_info_message(
        prize=settings.prize_name,
        total_tickets=settings.total_tickets,
        ticket_price=_format_money(settings.ticket_price),
    )

    context.user_data.pop("game_info_edit_mode", None)

    try:
        await query.edit_message_text("♻️ 'O'yin haqida' xabari standart holatga qaytarildi.")
    except TelegramError:
        pass

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="✅ Joriy ko'rinish:\n\n" + preview,
        reply_markup=admin_menu_keyboard(),
    )


async def admin_cancel(update: Update, context: CallbackContext) -> None:
    """Fallback handler to exit admin flows via /cancel."""
    context.user_data.pop("subscription_mode", None)
    context.user_data.pop("settings_mode", None)
    context.user_data.pop("broadcast_mode", None)
    context.user_data.pop("start_edit_mode", None)
    context.user_data.pop("game_info_edit_mode", None)
    await update.message.reply_text("❌ Jarayon bekor qilindi.", reply_markup=admin_menu_keyboard())


async def admin_active_mode_router(update: Update, context: CallbackContext) -> None:
    """Route incoming admin messages to active modes (broadcast/start edit)."""
    if context.user_data.get("broadcast_mode") == "awaiting_content":
        await admin_broadcast_handle_content(update, context)
        return
    if context.user_data.get("start_edit_mode"):
        await admin_start_message_handle_input(update, context)
        return
    if context.user_data.get("game_info_edit_mode"):
        await admin_game_info_message_handle_input(update, context)


async def _edit_admin_message(query, text: str) -> None:
    """Edit the admin's message caption or text."""
    message = query.message
    if message.photo or message.document:
        await query.edit_message_caption(caption=text, reply_markup=None)
    else:
        await query.edit_message_text(text=text, reply_markup=None)
