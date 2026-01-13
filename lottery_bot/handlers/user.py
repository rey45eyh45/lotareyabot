"""Handlers for user-facing interactions."""
from __future__ import annotations

import re
from typing import Optional, Tuple

from telegram import ReplyKeyboardRemove, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from lottery_bot.keyboards import (
    admin_decision_keyboard,
    cancel_keyboard,
    main_menu_keyboard,
    request_contact_keyboard,
    subscription_prompt_keyboard,
)
from lottery_bot.storage import StorageManager

WAITING_QUANTITY, WAITING_CONTACT, WAITING_RECEIPT = range(3)


def _format_currency(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def _normalize_phone(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 9:
        return None
    if raw.strip().startswith("+"):
        return "+" + digits
    if digits.startswith("998") and len(digits) == 12:
        return "+" + digits
    if len(digits) == 9:
        return "+998" + digits
    return "+" + digits


async def _ensure_subscription(update: Update, context: CallbackContext) -> bool:
    storage: StorageManager = context.application.bot_data["storage"]
    config = await storage.get_subscription_config()
    if not config["enabled"] or not config["channels"]:
        return True

    user = update.effective_user
    missing = []
    for channel in config["channels"]:
        chat_id = channel.get("id")
        if not chat_id:
            missing.append(channel)
            continue
        try:
            member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user.id)
        except Exception:
            missing.append(channel)
            continue

        status = getattr(member, "status", None)
        is_member = getattr(member, "is_member", None)
        if status in {"creator", "administrator", "member"} or is_member:
            continue
        missing.append(channel)

    if not missing:
        return True

    message_text = await storage.render_subscription_message(missing)
    keyboard = subscription_prompt_keyboard(missing or config["channels"])

    if update.callback_query:
        query = update.callback_query
        titles = ", ".join((channel.get("title") or channel.get("id") or "Kanal") for channel in missing)
        alert_text = "Avval quyidagi kanallarga obuna bo'ling: " + titles
        await query.answer(alert_text[:200], show_alert=True)
        try:
            await query.edit_message_text(message_text, reply_markup=keyboard, disable_web_page_preview=True)
        except BadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return False
            try:
                await query.message.reply_text(
                    message_text,
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
            except TelegramError:
                pass
        except TelegramError:
            try:
                await query.message.reply_text(
                    message_text,
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
            except TelegramError:
                pass
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    return False


async def _send_start_content(update: Update, context: CallbackContext, storage: StorageManager) -> None:
    settings = context.application.bot_data["settings"]
    remaining = await storage.remaining_tickets()
    content = await storage.render_start_content(
        prize=settings.prize_name,
        total_tickets=settings.total_tickets,
        remaining_tickets=remaining,
        ticket_price=_format_currency(settings.ticket_price),
    )

    media = content.get("media") if isinstance(content, dict) else None
    text = content.get("text") if isinstance(content, dict) else content
    message = update.message

    if media and media.get("type") == "photo":
        await message.reply_photo(
            photo=media.get("file_id"),
            caption=text,
            reply_markup=main_menu_keyboard(),
        )
    elif media and media.get("type") == "video":
        await message.reply_video(
            video=media.get("file_id"),
            caption=text,
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.reply_text(text, reply_markup=main_menu_keyboard())


async def start(update: Update, context: CallbackContext) -> None:
    """Show the welcome message and menu."""
    settings = context.application.bot_data["settings"]
    storage: StorageManager = context.application.bot_data["storage"]
    user = update.effective_user
    await storage.register_user(user.id, user.username, user.full_name)
    if not await _ensure_subscription(update, context):
        return
    await _send_start_content(update, context, storage)


async def buy_ticket_entry(update: Update, context: CallbackContext) -> int:
    """Ask the user how many tickets they want."""
    storage: StorageManager = context.application.bot_data["storage"]
    if not await _ensure_subscription(update, context):
        return ConversationHandler.END
    remaining = await storage.remaining_tickets()
    if remaining == 0:
        await update.message.reply_text(
            "😔 Kechirasiz, barcha chiptalar sotib bo'lingan. Natijalarni kuzatishda davom eting!"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🎟 Nechta chipta sotib olmoqchisiz? (1 dan {remaining} gacha son kiriting)".format(remaining=remaining),
        reply_markup=cancel_keyboard(),
    )
    return WAITING_QUANTITY


async def receive_quantity(update: Update, context: CallbackContext) -> int:
    """Validate desired quantity and show payment instructions."""
    text = (update.message.text or "").strip()
    storage: StorageManager = context.application.bot_data["storage"]
    if not await _ensure_subscription(update, context):
        return ConversationHandler.END
    remaining = await storage.remaining_tickets()

    if not text.isdigit():
        await update.message.reply_text("❗ Iltimos, faqat son kiriting.")
        return WAITING_QUANTITY

    quantity = int(text)
    if quantity < 1 or quantity > remaining:
        await update.message.reply_text(
            f"❗ Mavjud chipta soni: {remaining}. Shunga mos ravishda son kiriting."
        )
        return WAITING_QUANTITY

    settings = context.application.bot_data["settings"]
    payable = quantity * settings.ticket_price
    context.user_data["quantity"] = quantity
    context.user_data["payable"] = payable

    profile = await storage.get_user_profile(update.effective_user.id)
    phone_number = None
    if profile:
        phone_number = profile.get("phone_number")

    if phone_number:
        context.user_data["phone_number"] = phone_number
        await _send_payment_instructions(update, context, payable)
        return WAITING_RECEIPT

    await update.message.reply_text(
        "📞 Iltimos, bog'lanish uchun telefon raqamingizni yuboring.",
        reply_markup=request_contact_keyboard(),
    )
    return WAITING_CONTACT


async def _send_payment_instructions(update: Update, context: CallbackContext, payable: int) -> None:
    storage: StorageManager = context.application.bot_data["storage"]
    card_number = await storage.get_card_number()
    instructions = (
        "💳 To'lov qilish uchun quyidagi ma'lumotlardan foydalaning:\n"
        f"• Karta raqami: {card_number}\n"
        f"• To'lov summasi: {_format_currency(payable)} so'm\n\n"
        "To'lovni amalga oshirganingizdan so'ng, chekni botga rasm yoki fayl sifatida yuboring."
    )
    await update.message.reply_text(
        instructions,
        reply_markup=cancel_keyboard(),
    )


async def receive_contact(update: Update, context: CallbackContext) -> int:
    """Capture and persist the user's contact number."""
    contact = update.message.contact
    if contact and contact.user_id and contact.user_id != update.effective_user.id:
        await update.message.reply_text("❗ Faqat o'zingizning raqamingizni yuborishingiz mumkin.")
        return WAITING_CONTACT

    phone_raw = contact.phone_number if contact else (update.message.text or "").strip()
    phone_number = _normalize_phone(phone_raw)
    if not phone_number:
        await update.message.reply_text("❗ Telefon raqamni to'g'ri kiriting yoki tugma orqali yuboring.")
        return WAITING_CONTACT

    context.user_data["phone_number"] = phone_number
    settings = context.application.bot_data["settings"]
    storage: StorageManager = context.application.bot_data["storage"]
    user = update.effective_user
    await storage.register_user(user.id, user.username, user.full_name, phone_number=phone_number)

    payable = context.user_data.get("payable", settings.ticket_price)
    await _send_payment_instructions(update, context, payable)
    return WAITING_RECEIPT


def _extract_receipt(update: Update) -> Tuple[str | None, str | None]:
    """Return the file_id and type for a receipt message."""
    message = update.message
    if message.photo:
        return message.photo[-1].file_id, "photo"
    if message.document:
        return message.document.file_id, "document"
    return None, None


async def receive_receipt(update: Update, context: CallbackContext) -> int:
    """Persist pending purchase and notify admin."""
    receipt_file_id, receipt_type = _extract_receipt(update)
    if not receipt_file_id:
        await update.message.reply_text("Iltimos, chekni rasm yoki fayl shaklida yuboring.")
        return WAITING_RECEIPT

    quantity = context.user_data.pop("quantity", 1)
    user = update.effective_user
    settings = context.application.bot_data["settings"]
    storage: StorageManager = context.application.bot_data["storage"]

    phone_number = context.user_data.get("phone_number")
    if not phone_number:
        profile = await storage.get_user_profile(user.id)
        phone_number = profile.get("phone_number") if profile else None

    await storage.register_user(user.id, user.username, user.full_name, phone_number=phone_number)

    purchase_id = await storage.create_pending_purchase(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        phone_number=phone_number,
        quantity=quantity,
        ticket_price=settings.ticket_price,
        receipt_file_id=receipt_file_id,
        receipt_type=receipt_type,
    )

    username_line = f"📨 Username: @{user.username}\n" if user.username else "📨 Username: mavjud emas\n"
    phone_line = f"📞 Telefon: {phone_number}\n" if phone_number else ""
    caption = (
        "🆕 Yangi to'lov cheki keldi!\n\n"
        f"🆔 Purchase ID: {purchase_id}\n"
        f"👤 Foydalanuvchi: {user.full_name} (ID: {user.id})\n"
        f"{username_line}"
        f"{phone_line}"
        f"🎟 Chiptalar soni: {quantity}\n"
        f"💰 To'lov: {_format_currency(quantity * settings.ticket_price)} so'm"
    )

    if receipt_type == "photo":
        admin_message = await context.bot.send_photo(
            chat_id=settings.admin_id,
            photo=receipt_file_id,
            caption=caption,
            reply_markup=admin_decision_keyboard(purchase_id),
        )
    else:
        admin_message = await context.bot.send_document(
            chat_id=settings.admin_id,
            document=receipt_file_id,
            caption=caption,
            reply_markup=admin_decision_keyboard(purchase_id),
        )

    await storage.set_admin_message(
        purchase_id=purchase_id,
        chat_id=admin_message.chat_id,
        message_id=admin_message.message_id,
    )

    await update.message.reply_text(
        "✅ Rahmat! Chekingiz adminga yuborildi. Tasdiqlangach, chipta raqamingiz yuboriladi.",
        reply_markup=main_menu_keyboard(),
    )

    await context.bot.send_message(
        chat_id=settings.admin_id,
        text=f"📥 Yangi to'lov: {user.full_name} — {quantity} ta chipta.",
    )

    context.user_data.pop("phone_number", None)
    context.user_data.pop("payable", None)

    return ConversationHandler.END


async def cancel(update: Update, context: CallbackContext) -> int:
    """Allow user to exit the flow."""
    context.user_data.pop("quantity", None)
    context.user_data.pop("phone_number", None)
    context.user_data.pop("payable", None)
    await update.message.reply_text("⛔ Jarayon bekor qilindi.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def my_tickets(update: Update, context: CallbackContext) -> None:
    """Show all tickets owned by the user."""
    storage: StorageManager = context.application.bot_data["storage"]
    if not await _ensure_subscription(update, context):
        return
    tickets = await storage.get_user_tickets(update.effective_user.id)
    if not tickets:
        await update.message.reply_text("📭 Sizda hali tasdiqlangan chiptalar yo'q.")
        return

    formatted = ", ".join(str(ticket) for ticket in tickets)
    await update.message.reply_text(
        "🎟 Sizga biriktirilgan chiptalar:\n" + formatted,
        reply_markup=main_menu_keyboard(),
    )


async def game_info(update: Update, context: CallbackContext) -> None:
    """Provide basic information about the lottery."""
    if not await _ensure_subscription(update, context):
        return
    settings = context.application.bot_data["settings"]
    storage: StorageManager = context.application.bot_data["storage"]
    message = await storage.render_game_info_message(
        prize=settings.prize_name,
        total_tickets=settings.total_tickets,
        ticket_price=_format_currency(settings.ticket_price),
    )
    await update.message.reply_text(message, reply_markup=main_menu_keyboard())


def build_conversation_handler() -> ConversationHandler:
    """Configure the buy-ticket conversation handler."""
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🎟 Chiptani sotib olish$"), buy_ticket_entry),
            CommandHandler("buy", buy_ticket_entry),
        ],
        states={
            WAITING_QUANTITY: [
                MessageHandler(filters.Regex("^❌ Bekor qilish$"), cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_quantity),
            ],
            WAITING_CONTACT: [
                MessageHandler(filters.Regex("^❌ Bekor qilish$"), cancel),
                MessageHandler(filters.CONTACT, receive_contact),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_contact),
            ],
            WAITING_RECEIPT: [
                MessageHandler(filters.Regex("^❌ Bekor qilish$"), cancel),
                MessageHandler(
                    (filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
                    receive_receipt,
                ),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Bekor qilish$"), cancel),
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
    )


def register_user_handlers(application) -> None:
    """Attach user handlers to the application."""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(build_conversation_handler())
    application.add_handler(MessageHandler(filters.Regex("^📋 Mening chiptalarim$"), my_tickets))
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ O'yin haqida$"), game_info))
    application.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))


async def check_subscription_callback(update: Update, context: CallbackContext) -> None:
    """Re-run the subscription check when user clicks the inline button."""
    if await _ensure_subscription(update, context):
        query = update.callback_query
        await query.edit_message_text(
            "✅ Rahmat! Siz barcha kanallarga obuna bo'lgansiz. Endi botdan foydalanishingiz mumkin.",
        )
        storage: StorageManager = context.application.bot_data["storage"]
        settings = context.application.bot_data["settings"]
        remaining = await storage.remaining_tickets()
        content = await storage.render_start_content(
            prize=settings.prize_name,
            total_tickets=settings.total_tickets,
            remaining_tickets=remaining,
            ticket_price=_format_currency(settings.ticket_price),
        )
        media = content.get("media") if isinstance(content, dict) else None
        text = content.get("text") if isinstance(content, dict) else content
        chat_id = query.message.chat_id if query.message else query.from_user.id
        if media and media.get("type") == "photo":
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=media.get("file_id"),
                caption=text,
                reply_markup=main_menu_keyboard(),
            )
        elif media and media.get("type") == "video":
            await context.bot.send_video(
                chat_id=chat_id,
                video=media.get("file_id"),
                caption=text,
                reply_markup=main_menu_keyboard(),
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=main_menu_keyboard())
