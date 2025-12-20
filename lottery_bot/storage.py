"""Simple JSON-backed storage for the lottery bot."""
from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4


PurchaseData = Dict[str, Any]

DEFAULT_START_TEMPLATE = (
    "Lotareya botiga xush kelibsiz!\n\n"
    "🎁 Sovrin: {prize}\n"
    "🎟 Jami chipta: {total_tickets}\n"
    "✅ Qolgan chipta: {remaining_tickets}\n"
    "💸 Chipta narxi: {ticket_price} so'm\n\n"
    "Quyidagi tugmalar orqali kerakli bo'limni tanlang."
)

DEFAULT_SUBSCRIPTION_MESSAGE = (
    "Botdan to'liq foydalanish uchun quyidagi kanallarga obuna bo'ling:\n"
    "{channels}\n\n"
    "Obuna bo'lgach, '✅ Tekshirish' tugmasini bosing."
)

DEFAULT_GAME_INFO_MESSAGE = (
    "ℹ️ Lotareya shartlari:\n"
    "• Sovrin: {prize}\n"
    "• Jami chipta: {total_tickets} ta\n"
    "• Sotilgan chiptalar: {sold_tickets} ta\n"
    "• Qolgan chiptalar: {remaining_tickets} ta\n"
    "• Chipta narxi: {ticket_price} so'm\n\n"
    "To'lovingiz admin tomonidan tekshirilgach, chipta raqamlari yuboriladi."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StorageManager:
    """Manage ticket availability, purchases, analytics, and configuration."""

    def __init__(self, path: Path, total_tickets: int, *, default_card_number: str | None = None) -> None:
        self._path = path
        self._total_tickets = total_tickets
        self._default_card_number = default_card_number
        self._lock = asyncio.Lock()
        self._data = self._load()
        self._ensure_defaults(self._data)

    def _default_payload(self) -> Dict[str, Any]:
        tickets = list(range(1, self._total_tickets + 1))
        return {
            "available_tickets": tickets,
            "pending": {},
            "approved": {},
            "rejected": {},
            "user_tickets": {},
            "users": {},
            "meta": {
                "start_message": {"text": DEFAULT_START_TEMPLATE, "media": None},
                "subscription_message": DEFAULT_SUBSCRIPTION_MESSAGE,
                "manager_contact": "@menejer_1w",
                "game_info_message": DEFAULT_GAME_INFO_MESSAGE,
            },
            "subscriptions": {
                "enabled": False,
                "channels": [],
            },
        }

    def _ensure_defaults(self, payload: Dict[str, Any]) -> None:
        payload.setdefault("available_tickets", list(range(1, self._total_tickets + 1)))
        payload.setdefault("pending", {})
        payload.setdefault("approved", {})
        payload.setdefault("rejected", {})
        payload.setdefault("user_tickets", {})
        payload.setdefault("users", {})

        meta = payload.setdefault("meta", {})
        if "start_message" not in meta:
            legacy_template = meta.get("start_template", DEFAULT_START_TEMPLATE)
            meta["start_message"] = {"text": legacy_template, "media": None}
        else:
            meta["start_message"].setdefault("text", DEFAULT_START_TEMPLATE)
            meta["start_message"].setdefault("media", None)
        meta.setdefault("subscription_message", DEFAULT_SUBSCRIPTION_MESSAGE)
        if "card_number" not in meta:
            meta["card_number"] = self._default_card_number or ""
        meta.setdefault("manager_contact", "@menejer_1w")
        meta.setdefault("game_info_message", DEFAULT_GAME_INFO_MESSAGE)

        subs = payload.setdefault("subscriptions", {})
        subs.setdefault("enabled", False)
        subs.setdefault("channels", [])

    def _load(self) -> Dict[str, Any]:
        if not self._path.exists():
            payload = self._default_payload()
            self._persist(payload)
            return payload

        with self._path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        # Defensive tidy-up to guard against manual edits.
        available = payload.get("available_tickets", [])
        payload["available_tickets"] = sorted({int(t) for t in available})
        return payload

    def _persist(self, payload: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    async def register_user(
        self,
        user_id: int,
        username: Optional[str],
        full_name: Optional[str],
        phone_number: Optional[str] = None,
    ) -> None:
        """Create or update a user record for analytics."""

        async with self._lock:
            now_iso = _now().isoformat()
            record = self._data["users"].get(str(user_id))
            if not record:
                record = {
                    "user_id": user_id,
                    "username": username,
                    "full_name": full_name,
                    "phone_number": phone_number,
                    "first_seen": now_iso,
                    "last_active": now_iso,
                    "purchases": 0,
                    "total_tickets": 0,
                    "total_spent": 0,
                    "history": [],
                }
                self._data["users"][str(user_id)] = record
            else:
                if username is not None:
                    record["username"] = username
                if full_name:
                    record["full_name"] = full_name
                if phone_number:
                    record["phone_number"] = phone_number
                record["last_active"] = now_iso
            self._persist(self._data)

    async def remaining_tickets(self) -> int:
        async with self._lock:
            return len(self._data["available_tickets"])

    async def list_available_tickets(self) -> List[int]:
        async with self._lock:
            return list(self._data["available_tickets"])

    async def create_pending_purchase(
        self,
        user_id: int,
        username: Optional[str],
        full_name: Optional[str],
        phone_number: Optional[str],
        quantity: int,
        ticket_price: int,
        receipt_file_id: str,
        receipt_type: str,
    ) -> str:
        async with self._lock:
            purchase_id = uuid4().hex
            now_iso = _now().isoformat()
            payload = {
                "purchase_id": purchase_id,
                "user_id": user_id,
                "username": username,
                "full_name": full_name,
                "phone_number": phone_number,
                "quantity": quantity,
                "ticket_price": ticket_price,
                "amount": ticket_price * quantity,
                "receipt_file_id": receipt_file_id,
                "receipt_type": receipt_type,
                "created_at": now_iso,
                "status": "pending",
            }
            self._data["pending"][purchase_id] = payload
            self._persist(self._data)
            return purchase_id

    async def set_admin_message(self, purchase_id: str, chat_id: int, message_id: int) -> None:
        async with self._lock:
            purchase = self._data["pending"].get(purchase_id)
            if not purchase:
                return
            purchase["admin_message"] = {
                "chat_id": chat_id,
                "message_id": message_id,
            }
            self._persist(self._data)

    async def is_pending(self, purchase_id: str) -> bool:
        async with self._lock:
            return purchase_id in self._data["pending"]

    async def approve_purchase(self, purchase_id: str) -> Tuple[List[int], PurchaseData]:
        async with self._lock:
            purchase = self._data["pending"].pop(purchase_id, None)
            if not purchase:
                return [], {}

            quantity = purchase["quantity"]
            available = self._data["available_tickets"]
            if len(available) < quantity:
                # Put it back and signal the caller to handle shortage.
                self._data["pending"][purchase_id] = purchase
                return [], {}

            tickets = random.sample(available, quantity)
            for ticket in tickets:
                available.remove(ticket)

            user_bucket = self._data["user_tickets"].setdefault(str(purchase["user_id"]), [])
            user_bucket.extend(tickets)

            now_iso = _now().isoformat()
            purchase.update(
                {
                    "status": "approved",
                    "tickets": tickets,
                    "resolved_at": now_iso,
                }
            )
            self._data["approved"][purchase_id] = purchase

            # Update user analytics bucket.
            user_record = self._data["users"].setdefault(
                str(purchase["user_id"]),
                {
                    "user_id": purchase["user_id"],
                    "username": purchase.get("username"),
                    "full_name": purchase.get("full_name"),
                    "phone_number": purchase.get("phone_number"),
                    "first_seen": now_iso,
                    "last_active": now_iso,
                    "purchases": 0,
                    "total_tickets": 0,
                    "total_spent": 0,
                    "history": [],
                },
            )
            user_record["purchases"] = user_record.get("purchases", 0) + 1
            user_record["total_tickets"] = user_record.get("total_tickets", 0) + quantity
            user_record["total_spent"] = user_record.get("total_spent", 0) + purchase.get("amount", 0)
            user_record["last_active"] = now_iso
            if purchase.get("phone_number"):
                user_record["phone_number"] = purchase["phone_number"]
            history = user_record.setdefault("history", [])
            history.append(
                {
                    "purchase_id": purchase_id,
                    "tickets": tickets,
                    "amount": purchase.get("amount", 0),
                    "quantity": quantity,
                    "resolved_at": now_iso,
                }
            )

            self._persist(self._data)
            return tickets, purchase

    async def reject_purchase(self, purchase_id: str) -> PurchaseData:
        async with self._lock:
            purchase = self._data["pending"].pop(purchase_id, None)
            if not purchase:
                return {}

            purchase.update(
                {
                    "status": "rejected",
                    "resolved_at": _now().isoformat(),
                }
            )
            self._data["rejected"][purchase_id] = purchase

            # Mark user as active even if rejected.
            record = self._data["users"].get(str(purchase["user_id"]))
            if record:
                record["last_active"] = _now().isoformat()

            self._persist(self._data)
            return purchase

    async def list_approved(self) -> List[PurchaseData]:
        async with self._lock:
            return [dict(item) for item in self._data["approved"].values()]

    async def cancel_approved_purchase(self, purchase_id: str) -> PurchaseData:
        """Revoke an approved purchase, freeing tickets and updating analytics."""
        async with self._lock:
            purchase = self._data["approved"].pop(purchase_id, None)
            if not purchase:
                return {}

            tickets = purchase.get("tickets", []) or []

            # Return tickets to availability.
            available = self._data.setdefault("available_tickets", [])
            available.extend(tickets)
            available[:] = sorted(set(available))

            # Remove tickets from user's bucket.
            user_bucket = self._data.setdefault("user_tickets", {}).get(str(purchase.get("user_id")), [])
            if user_bucket:
                remaining = [t for t in user_bucket if t not in tickets]
                self._data["user_tickets"][str(purchase.get("user_id"))] = remaining

            # Adjust user stats.
            user_record = self._data.get("users", {}).get(str(purchase.get("user_id")))
            if user_record:
                user_record["purchases"] = max(0, user_record.get("purchases", 0) - 1)
                user_record["total_tickets"] = max(0, user_record.get("total_tickets", 0) - len(tickets))
                user_record["total_spent"] = max(0, user_record.get("total_spent", 0) - purchase.get("amount", 0))
                user_record["last_active"] = _now().isoformat()
                history = user_record.setdefault("history", [])
                history.append(
                    {
                        "purchase_id": purchase_id,
                        "tickets": list(tickets),
                        "amount": purchase.get("amount", 0),
                        "quantity": purchase.get("quantity", 0),
                        "resolved_at": _now().isoformat(),
                        "status": "cancelled",
                    }
                )

            purchase.update({"status": "cancelled", "cancelled_at": _now().isoformat()})
            self._persist(self._data)
            return purchase

    async def get_user_tickets(self, user_id: int) -> List[int]:
        async with self._lock:
            return sorted(self._data["user_tickets"].get(str(user_id), []))

    async def get_summary(self) -> Dict[str, Any]:
        async with self._lock:
            remaining = len(self._data["available_tickets"])
            sold = self._total_tickets - remaining
            revenue = sum(item.get("amount", 0) for item in self._data["approved"].values())
            return {
                "total": self._total_tickets,
                "sold": sold,
                "remaining": remaining,
                "pending_count": len(self._data["pending"]),
                "revenue": revenue,
            }

    async def get_detailed_stats(self) -> Dict[str, Any]:
        async with self._lock:
            now = _now()
            users = list(self._data["users"].values())
            total_users = len(users)
            active_24h = 0
            new_24h = 0
            total_tickets_sold = 0
            total_revenue = 0
            total_purchases = 0

            twenty_four_hours_ago = now - timedelta(hours=24)

            for record in users:
                last_active_raw = record.get("last_active")
                if last_active_raw:
                    try:
                        if datetime.fromisoformat(last_active_raw) >= twenty_four_hours_ago:
                            active_24h += 1
                    except ValueError:
                        pass

                first_seen_raw = record.get("first_seen")
                if first_seen_raw:
                    try:
                        if datetime.fromisoformat(first_seen_raw) >= twenty_four_hours_ago:
                            new_24h += 1
                    except ValueError:
                        pass
                total_tickets_sold += int(record.get("total_tickets", 0))
                total_revenue += int(record.get("total_spent", 0))
                total_purchases += int(record.get("purchases", 0))

            pending_amount = sum(item.get("amount", 0) for item in self._data["pending"].values())
            approved_count = len(self._data["approved"])
            rejected_count = len(self._data["rejected"])

            top_users = sorted(
                (
                    {
                        "user_id": record.get("user_id"),
                        "full_name": record.get("full_name"),
                        "username": record.get("username"),
                        "tickets": int(record.get("total_tickets", 0)),
                        "spent": int(record.get("total_spent", 0)),
                    }
                    for record in users
                    if int(record.get("total_tickets", 0)) > 0
                ),
                key=lambda item: (item["tickets"], item["spent"]),
                reverse=True,
            )[:5]

            remaining = len(self._data["available_tickets"])

            avg_tickets_per_user = total_tickets_sold / total_users if total_users else 0.0
            avg_spend_per_user = total_revenue / total_users if total_users else 0.0

            return {
                "total_tickets": self._total_tickets,
                "remaining_tickets": remaining,
                "tickets_sold": total_tickets_sold,
                "total_revenue": total_revenue,
                "pending_amount": pending_amount,
                "pending_count": len(self._data["pending"]),
                "approved_count": approved_count,
                "rejected_count": rejected_count,
                "total_users": total_users,
                "active_users_24h": active_24h,
                "new_users_24h": new_24h,
                "total_purchases": total_purchases,
                "avg_tickets_per_user": avg_tickets_per_user,
                "avg_spend_per_user": avg_spend_per_user,
                "top_users": top_users,
            }

    async def list_pending(self) -> List[PurchaseData]:
        async with self._lock:
            return [dict(item) for item in self._data["pending"].values()]

    async def list_user_ids(self) -> List[int]:
        async with self._lock:
            result: List[int] = []
            for user_id in self._data["users"].keys():
                try:
                    result.append(int(user_id))
                except (TypeError, ValueError):
                    continue
            return result

    async def get_user_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with self._lock:
            record = self._data["users"].get(str(user_id))
            return dict(record) if record else None

    @staticmethod
    def _validate_template(text: str, required_keys: List[str]) -> None:
        if not text.strip():
            raise ValueError("Matn bo'sh bo'lishi mumkin emas.")
        payload = {key: f"__{key}__" for key in required_keys}
        try:
            text.format(**payload)
        except KeyError as exc:
            raise ValueError(f"Noma'lum o'zgaruvchi: {exc.args[0]}") from exc
        except Exception as exc:  # pragma: no cover - formatting safeguards
            raise ValueError("Shablonni formatlashda xatolik yuz berdi.") from exc

    async def set_start_message(self, *, text: str, media: Optional[Dict[str, str]]) -> None:
        self._validate_template(text, ["prize", "total_tickets", "remaining_tickets", "ticket_price"])
        async with self._lock:
            meta = self._data.setdefault("meta", {})
            meta["start_message"] = {"text": text, "media": media}
            self._persist(self._data)

    async def render_start_content(
        self,
        *,
        prize: str,
        total_tickets: int,
        remaining_tickets: int,
        ticket_price: str,
    ) -> Dict[str, Any]:
        async with self._lock:
            start_cfg = self._data.setdefault("meta", {}).get(
                "start_message", {"text": DEFAULT_START_TEMPLATE, "media": None}
            )
        text = start_cfg.get("text", DEFAULT_START_TEMPLATE).format(
            prize=prize,
            total_tickets=total_tickets,
            remaining_tickets=remaining_tickets,
            ticket_price=ticket_price,
        )
        media = start_cfg.get("media")
        return {"text": text, "media": media}

    async def set_subscription_message(self, text: str) -> None:
        self._validate_template(text, ["channels"])
        async with self._lock:
            self._data.setdefault("meta", {})["subscription_message"] = text
            self._persist(self._data)

    async def set_game_info_message(self, text: str) -> None:
        self._validate_template(
            text,
            ["prize", "total_tickets", "sold_tickets", "remaining_tickets", "ticket_price"],
        )
        async with self._lock:
            self._data.setdefault("meta", {})["game_info_message"] = text
            self._persist(self._data)

    async def reset_game_info_message(self) -> str:
        async with self._lock:
            self._data.setdefault("meta", {})["game_info_message"] = DEFAULT_GAME_INFO_MESSAGE
            self._persist(self._data)
            return DEFAULT_GAME_INFO_MESSAGE

    async def set_card_number(self, card_number: str) -> None:
        async with self._lock:
            meta = self._data.setdefault("meta", {})
            meta["card_number"] = card_number.strip()
            self._persist(self._data)

    async def get_card_number(self) -> str:
        async with self._lock:
            return self._data.setdefault("meta", {}).get("card_number") or ""

    async def set_manager_contact(self, username: str) -> None:
        async with self._lock:
            meta = self._data.setdefault("meta", {})
            meta["manager_contact"] = username.strip()
            self._persist(self._data)

    async def get_manager_contact(self) -> str:
        async with self._lock:
            return self._data.setdefault("meta", {}).get("manager_contact") or "@menejer_1w"

    async def get_subscription_message(self) -> str:
        async with self._lock:
            return self._data.setdefault("meta", {}).get("subscription_message", DEFAULT_SUBSCRIPTION_MESSAGE)

    async def get_game_info_message(self) -> str:
        async with self._lock:
            return self._data.setdefault("meta", {}).get("game_info_message", DEFAULT_GAME_INFO_MESSAGE)

    async def render_game_info_message(
        self,
        *,
        prize: str,
        total_tickets: int,
        ticket_price: str,
    ) -> str:
        async with self._lock:
            template = self._data.setdefault("meta", {}).get("game_info_message", DEFAULT_GAME_INFO_MESSAGE)
            remaining = len(self._data["available_tickets"])
        sold = max(0, total_tickets - remaining)
        return template.format(
            prize=prize,
            total_tickets=total_tickets,
            sold_tickets=sold,
            remaining_tickets=remaining,
            ticket_price=ticket_price,
        )

    async def get_subscription_config(self) -> Dict[str, Any]:
        async with self._lock:
            subs = self._data.setdefault("subscriptions", {})
            return {
                "enabled": bool(subs.get("enabled", False)),
                "channels": [dict(item) for item in subs.get("channels", [])],
            }

    async def set_subscription_enabled(self, enabled: bool) -> None:
        async with self._lock:
            subs = self._data.setdefault("subscriptions", {})
            subs["enabled"] = bool(enabled)
            self._persist(self._data)

    async def add_subscription_channel(self, channel_id: str, title: str, link: Optional[str]) -> None:
        async with self._lock:
            subs = self._data.setdefault("subscriptions", {})
            channels = subs.setdefault("channels", [])
            for item in channels:
                if item.get("id") == channel_id:
                    item.update({"title": title, "link": link})
                    break
            else:
                channels.append({"id": channel_id, "title": title, "link": link})
            self._persist(self._data)

    async def remove_subscription_channel(self, channel_id: str) -> bool:
        async with self._lock:
            subs = self._data.setdefault("subscriptions", {})
            channels = subs.setdefault("channels", [])
            original_len = len(channels)
            subs["channels"] = [item for item in channels if item.get("id") != channel_id]
            changed = len(subs["channels"]) != original_len
            if changed:
                self._persist(self._data)
            return changed

    async def get_ticket_export_rows(self) -> List[Dict[str, Any]]:
        async with self._lock:
            rows: List[Dict[str, Any]] = []
            for purchase in self._data["approved"].values():
                rows.append(
                    {
                        "purchase_id": purchase.get("purchase_id"),
                        "full_name": purchase.get("full_name"),
                        "username": purchase.get("username"),
                        "phone_number": purchase.get("phone_number"),
                        "quantity": purchase.get("quantity", 0),
                        "tickets": list(purchase.get("tickets", [])),
                        "amount": purchase.get("amount", 0),
                        "resolved_at": purchase.get("resolved_at"),
                    }
                )
            return rows

    async def render_subscription_message(self, channels_override: Optional[List[Dict[str, Any]]] = None) -> str:
        async with self._lock:
            message_template = self._data.setdefault("meta", {}).get(
                "subscription_message", DEFAULT_SUBSCRIPTION_MESSAGE
            )
            if channels_override is not None:
                channels = channels_override
            else:
                channels = self._data.setdefault("subscriptions", {}).setdefault("channels", [])
        if channels:
            lines = [f"• {channel.get('title') or channel.get('id')}" for channel in channels]
            channels_block = "\n".join(lines)
        else:
            channels_block = "• Kanallar qo'shilmagan"
        return message_template.format(channels=channels_block)
