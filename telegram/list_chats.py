"""Показать чаты Telegram — скопируй ID в TELEGRAM_CHATS."""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient

import config
from telegram.session import (
    SESSION_PATH,
    restore_session_from_env,
    save_meta,
    should_reset_session,
    wipe_session_files,
)

load_dotenv()


def _code_callback() -> str:
    code = os.getenv("TELEGRAM_CODE", "").strip()
    return code or input("Код из Telegram: ").strip()


def _password_callback() -> str:
    pwd = os.getenv("TELEGRAM_PASSWORD", "").strip()
    return pwd or input("Пароль 2FA Telegram: ").strip()


async def main() -> None:
    api_id = int(os.getenv("TELEGRAM_API_ID", "") or config.TELEGRAM_API_ID or 0)
    api_hash = os.getenv("TELEGRAM_API_HASH", "") or config.TELEGRAM_API_HASH
    phone = (os.getenv("TELEGRAM_PHONE", "") or config.TELEGRAM_PHONE).strip()

    if not api_id or not api_hash:
        raise SystemExit("Заполните TELEGRAM_API_ID и TELEGRAM_API_HASH в .env")

    restore_session_from_env()

    reset, reason = should_reset_session(phone, api_id)
    if reset:
        wipe_session_files()
        print(f"Сброс сессии: {reason}\n")

    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    await client.start(
        phone=phone or None,
        code_callback=_code_callback,
        password=_password_callback,
    )

    me = await client.get_me()
    if phone:
        save_meta(phone=phone, user_id=me.id, api_id=api_id)
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
        "или @username канала.\n\n"
        "Для Railway: python tg_export_session.py"
    )


if __name__ == "__main__":
    asyncio.run(main())
