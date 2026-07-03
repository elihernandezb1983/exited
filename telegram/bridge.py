"""Telegram → Discord: только сообщения о войнах."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

import config
from core.console_log import detail, info
from telegram.session import (
    SESSION_PATH,
    load_meta,
    print_session_dump_for_railway,
    restore_session_from_env,
    save_meta,
    should_reset_session,
    wipe_session_files,
    can_prompt_for_code,
)

if TYPE_CHECKING:
    from bot import GlowBot

log = logging.getLogger(__name__)


class TelegramBridge:
    def __init__(self, discord_bot: GlowBot) -> None:
        self.discord_bot = discord_bot
        self.client: TelegramClient | None = None
        self._watch_chats: list = []

    @staticmethod
    def is_enabled() -> bool:
        flag = os.getenv("TELEGRAM_ENABLED", "false").lower()
        if flag not in ("1", "true", "yes", "on"):
            return False
        api_id = os.getenv("TELEGRAM_API_ID", "") or str(config.TELEGRAM_API_ID or "")
        api_hash = os.getenv("TELEGRAM_API_HASH", "") or config.TELEGRAM_API_HASH
        return bool(api_id and api_hash)

    def _chat_sources(self) -> list[str]:
        raw = os.getenv("TELEGRAM_CHATS", "") or os.getenv("TELEGRAM_CHAT_IDS", "")
        if not raw and config.TELEGRAM_CHATS:
            raw = ",".join(config.TELEGRAM_CHATS)
        return [p.strip() for p in raw.split(",") if p.strip()]

    @staticmethod
    def _extract_text(message) -> str:
        text = (message.message or message.text or "").strip()
        if text:
            return text
        if getattr(message, "raw_text", None):
            return str(message.raw_text).strip()
        return ""

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        if not event.message:
            return
        text = self._extract_text(event.message)
        if not text:
            return

        debug = os.getenv("TELEGRAM_DEBUG", "").lower() in ("1", "true", "yes")
        if debug:
            direction = "исх." if event.out else "вх."
            preview = text.replace("\n", " ")[:80]
            detail(f"TG [{event.chat_id}] {direction}: {preview}")

        handler = getattr(self.discord_bot, "war_handler", None)
        if not handler:
            return
        try:
            await handler.handle_telegram_text(text)
        except Exception:
            log.exception("Ошибка обработки войны из Telegram")

    async def _print_dialogs_hint(self) -> None:
        assert self.client is not None
        print("\nТвои чаты (скопируй ID в TELEGRAM_CHATS):")
        async for dialog in self.client.iter_dialogs(limit=30):
            ent = dialog.entity
            uname = f" @{ent.username}" if getattr(ent, "username", None) else ""
            hint = ""
            if "организа" in (dialog.name or "").lower():
                hint = " ← войны?"
            print(f"  {dialog.id:>14} | {dialog.name}{uname}{hint}")
        print()

    async def _dialog_index(self) -> dict[int, object]:
        """Кэш диалогов — нужен для ЛС (PeerUser без access_hash)."""
        assert self.client is not None
        index: dict[int, object] = {}
        async for dialog in self.client.iter_dialogs(limit=None):
            index[dialog.id] = dialog.entity
            ent = dialog.entity
            ent_id = getattr(ent, "id", None)
            if ent_id is not None:
                index[int(ent_id)] = ent
        return index

    async def _resolve_entity(self, src: str, dialogs: dict[int, object]):
        assert self.client is not None
        src = src.strip()
        if not src:
            raise ValueError("пустой ID")

        if src.startswith("@"):
            return await self.client.get_entity(src)

        if src.lstrip("-").isdigit():
            num = int(src)
            # ЛС: id совпадает с dialog.id в списке чатов
            if num in dialogs:
                return dialogs[num]
            if -num in dialogs:
                return dialogs[-num]
            return await self.client.get_entity(num)

        return await self.client.get_entity(src)

    @staticmethod
    def _chat_label(entity: object, fallback: str) -> str:
        title = getattr(entity, "title", None)
        if title:
            return str(title)
        first = getattr(entity, "first_name", None) or fallback
        last = getattr(entity, "last_name", "") or ""
        uname = getattr(entity, "username", None)
        name = f"{first} {last}".strip()
        if uname:
            return f"{name} (@{uname})".strip()
        return name or fallback

    async def _resolve_watch_chats(self) -> list:
        assert self.client is not None
        resolved: list = []
        dialogs = await self._dialog_index()

        for src in self._chat_sources():
            try:
                entity = await self._resolve_entity(src, dialogs)
                resolved.append(entity)
                kind = "ЛС" if getattr(entity, "first_name", None) else "чат"
                label = self._chat_label(entity, src)
                info(f"TG: {label}")
            except Exception as exc:
                info(f"TG ✗ «{src}»: {exc}")
        return resolved

    def _code_callback(self) -> str:
        code = os.getenv("TELEGRAM_CODE", "").strip()
        return code or input("Код из Telegram: ").strip()

    def _password_callback(self) -> str:
        pwd = os.getenv("TELEGRAM_PASSWORD", "").strip()
        return pwd or input("Пароль 2FA Telegram: ").strip()

    async def start(self) -> None:
        api_id = int(os.getenv("TELEGRAM_API_ID", "") or config.TELEGRAM_API_ID or 0)
        api_hash = os.getenv("TELEGRAM_API_HASH", "") or config.TELEGRAM_API_HASH
        phone = (os.getenv("TELEGRAM_PHONE", "") or config.TELEGRAM_PHONE).strip()

        if not api_id or not api_hash:
            print("Telegram: нужны TELEGRAM_API_ID и TELEGRAM_API_HASH")
            return

        restore_session_from_env()

        reset, reason = should_reset_session(phone, api_id)
        if reset:
            wipe_session_files()
            print(f"Telegram: сброс сессии — {reason}")

        SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
        await self.client.connect()

        if not await self.client.is_user_authorized():
            if not phone:
                print("Telegram: укажите TELEGRAM_PHONE в .env")
                await self.client.disconnect()
                self.client = None
                return
            if not can_prompt_for_code():
                print(
                    "Telegram: сессия не авторизована. На Railway укажите TELEGRAM_CODE "
                    "(один деплой) или TELEGRAM_SESSION_B64 после локального логина."
                )
                await self.client.disconnect()
                self.client = None
                return
            await self.client.disconnect()
            wipe_session_files()
            self.client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
            await self.client.connect()
            try:
                await self.client.start(
                    phone=phone,
                    code_callback=self._code_callback,
                    password=self._password_callback,
                )
            except FloodWaitError as exc:
                hours = exc.seconds // 3600
                mins = (exc.seconds % 3600) // 60
                print(
                    f"Telegram: FloodWait — слишком много запросов кода, "
                    f"подождите ~{hours} ч {mins} мин ({exc.seconds} с). "
                    "Discord продолжит работу без TG."
                )
                await self.client.disconnect()
                self.client = None
                return

        if not await self.client.is_user_authorized():
            await self.client.disconnect()
            self.client = None
            return

        me = await self.client.get_me()
        if phone:
            save_meta(phone=phone, user_id=me.id, api_id=api_id)

        if os.getenv("TELEGRAM_DUMP_SESSION", "").lower() in ("1", "true", "yes", "on"):
            print_session_dump_for_railway()

        self._watch_chats = await self._resolve_watch_chats()
        if not self._watch_chats:
            await self._print_dialogs_hint()
            info("TG: укажите TELEGRAM_CHATS в .env")
            return

        self.client.add_event_handler(
            self._on_new_message,
            events.NewMessage(chats=self._watch_chats),
        )
        info(f"TG: {me.first_name}, {len(self._watch_chats)} чат(ов)")

    async def stop(self) -> None:
        if self.client:
            await self.client.disconnect()
            self.client = None
