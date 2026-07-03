"""Файл сессии Telethon."""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import config

SESSION_PATH = config.BASE_DIR / "data" / "telegram_user"
META_PATH = config.BASE_DIR / "data" / "telegram_account.json"
SESSION_FILE = Path(str(SESSION_PATH) + ".session")


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


def restore_session_from_env() -> bool:
    """Восстановить сессию из Railway/env (TELEGRAM_SESSION_B64 + meta)."""
    session_b64 = os.getenv("TELEGRAM_SESSION_B64", "").strip()
    meta_b64 = os.getenv("TELEGRAM_META_B64", "").strip()
    meta_json = os.getenv("TELEGRAM_ACCOUNT_JSON", "").strip()

    if not session_b64 and not meta_b64 and not meta_json:
        return False

    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    wrote = False

    if session_b64:
        SESSION_FILE.write_bytes(base64.b64decode(session_b64))
        wrote = True

    if meta_json:
        META_PATH.write_text(meta_json, encoding="utf-8")
        wrote = True
    elif meta_b64:
        META_PATH.write_bytes(base64.b64decode(meta_b64))
        wrote = True

    return wrote


def export_session_env_lines() -> list[str]:
    """Строки для .env / Railway Variables."""
    if not SESSION_FILE.is_file():
        raise FileNotFoundError(
            "Нет data/telegram_user.session — сначала: python tg_list_chats.py"
        )

    lines = [
        "TELEGRAM_SESSION_B64="
        + base64.b64encode(SESSION_FILE.read_bytes()).decode("ascii"),
    ]
    if META_PATH.is_file():
        lines.append(
            "TELEGRAM_META_B64="
            + base64.b64encode(META_PATH.read_bytes()).decode("ascii"),
        )
    return lines


def print_session_dump_for_railway() -> None:
    """Один раз после логина: скопировать из Deploy Logs в Railway Variables."""
    lines = export_session_env_lines()
    print("\n=== TELEGRAM SESSION (скопируй в Railway Variables, потом убери TELEGRAM_CODE) ===")
    for line in lines:
        print(line)
    print("=== конец ===\n")


def relogin_requested() -> bool:
    return os.getenv("TELEGRAM_RELOGIN", "").lower() in ("1", "true", "yes", "on")


def should_reset_session(phone: str, api_id: int) -> tuple[bool, str]:
    if relogin_requested():
        return True, "в .env включён TELEGRAM_RELOGIN=true"

    meta = load_meta()
    if phone and SESSION_FILE.is_file() and not meta:
        if os.getenv("TELEGRAM_SESSION_B64", "").strip():
            return False, ""
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
