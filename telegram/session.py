"""Файл сессии Telethon."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import config

SESSION_PATH = config.BASE_DIR / "data" / "telegram_user"
META_PATH = config.BASE_DIR / "data" / "telegram_account.json"


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def load_meta() -> dict[str, Any] | None:
    if not META_PATH.is_file():
        return None
    try:
        with META_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def save_meta(*, phone: str, user_id: int, api_id: int) -> None:
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"phone": phone, "user_id": user_id, "api_id": api_id}
    with META_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def relogin_requested() -> bool:
    return os.getenv("TELEGRAM_RELOGIN", "").lower() in ("1", "true", "yes", "on")


def should_reset_session(phone: str, api_id: int) -> tuple[bool, str]:
    if relogin_requested():
        return True, "в .env включён TELEGRAM_RELOGIN=true"

    meta = load_meta()
    session_file = Path(str(SESSION_PATH) + ".session")
    if phone and session_file.is_file() and not meta:
        return True, "в .env указан номер, но сессия ещё не привязана"

    if not meta:
        return False, ""

    if api_id and meta.get("api_id") and int(meta["api_id"]) != int(api_id):
        return True, "изменился TELEGRAM_API_ID"

    if phone and meta.get("phone"):
        saved = normalize_phone(str(meta["phone"]))
        current = normalize_phone(phone)
        if saved and current and saved != current:
            return True, f"в .env другой номер ({phone}), в сессии был {meta['phone']}"

    return False, ""


def wipe_session_files() -> list[str]:
    removed: list[str] = []
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    prefix = SESSION_PATH.name
    for path in SESSION_PATH.parent.iterdir():
        if path.name == prefix or path.name.startswith(prefix + "."):
            try:
                path.unlink()
                removed.append(path.name)
            except OSError:
                pass
    if META_PATH.is_file():
        try:
            META_PATH.unlink()
            removed.append(META_PATH.name)
        except OSError:
            pass
    return removed
