"""Показать чаты Telegram — скопируй ID в TELEGRAM_CHATS."""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient

import config
from telegram.session import SESSION_PATH, should_reset_session, wipe_session_files

load_dotenv()


async def main() -> None:
    api_id = int(os.getenv("TELEGRAM_API_ID", "") or config.TELEGRAM_API_ID or 0)
    api_hash = os.getenv("TELEGRAM_API_HASH", "") or config.TELEGRAM_API_HASH
    phone = (os.getenv("TELEGRAM_PHONE", "") or config.TELEGRAM_PHONE).strip()

    if not api_id or not api_hash:
        raise SystemExit("Заполните TELEGRAM_API_ID и TELEGRAM_API_HASH в .env")

    reset, reason = should_reset_session(phone, api_id)
    if reset:
        wipe_session_files()
        print(f"Сброс сессии: {reason}\n")

    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    await client.start(phone=phone or None)

    me = await client.get_me()
    print(f"Аккаунт: {me.first_name} (@{me.username})\n")
    print("ID              | Тип        | Название")
    print("-" * 60)

    async for dialog in client.iter_dialogs(limit=80):
        ent = dialog.entity
        kind = type(ent).__name__
        uname = f" @{ent.username}" if getattr(ent, "username", None) else ""
        marker = ""
        name_lower = (dialog.name or "").lower()
        if "организа" in name_lower or "событ" in name_lower:
            marker = "  ← часто это чат войн"
        print(f"{dialog.id:>14} | {kind:10} | {dialog.name}{uname}{marker}")

    await client.disconnect()
    print(
        "\nВ .env укажите ID строкой (как в таблице), например:\n"
        "  TELEGRAM_CHATS=-1001234567890\n"
        "или @username канала."
    )


if __name__ == "__main__":
    asyncio.run(main())
