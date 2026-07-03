"""Сохранение настроек серверов."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import config

DATA_DIR = config.BASE_DIR / "data"
DATA_FILE = DATA_DIR / "guilds.json"
_lock = threading.Lock()


def _default_guild() -> dict[str, Any]:
    return {
        "ticket_category_id": None,
        "staff_role_ids": [],
        "moderator_role_ids": [],
        "accepted_role_id": None,
        "next_ticket_number": 1,
        "ticket_cooldowns": {},
        "contracts_by_message": {},
        "gatherings_by_message": {},
        "afk_users": {},
        "war_channel_id": None,
        "war_report_channel_id": None,
        "war_cd_channel_id": None,
        "log_actions_channel_id": None,
        "log_usage_channel_id": None,
        "audit_log_enabled": True,
        "war": None,
    }


def get_all_guilds() -> dict[str, dict[str, Any]]:
    return _load_all().get("guilds", {})


def _load_all_unlocked() -> dict[str, Any]:
    if not DATA_FILE.is_file():
        return {"guilds": {}}
    with DATA_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def _save_all_unlocked(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_all() -> dict[str, Any]:
    with _lock:
        return _load_all_unlocked()


def _save_all(data: dict[str, Any]) -> None:
    with _lock:
        _save_all_unlocked(data)


def get_guild(guild_id: int) -> dict[str, Any]:
    with _lock:
        data = _load_all_unlocked()
        key = str(guild_id)
        if key not in data.setdefault("guilds", {}):
            data["guilds"][key] = _default_guild()
            _save_all_unlocked(data)
        return dict(data["guilds"][key])


def update_guild(guild_id: int, **fields: Any) -> dict[str, Any]:
    with _lock:
        data = _load_all_unlocked()
        key = str(guild_id)
        guild = data.setdefault("guilds", {}).setdefault(key, _default_guild())
        guild.update(fields)
        _save_all_unlocked(data)
        return dict(guild)


def mutate_guild(guild_id: int, mutator) -> dict[str, Any]:
    """Изменить настройки сервера через callable(guild_dict) -> None."""
    with _lock:
        data = _load_all_unlocked()
        key = str(guild_id)
        guild = data.setdefault("guilds", {}).setdefault(key, _default_guild())
        mutator(guild)
        _save_all_unlocked(data)
        return dict(guild)
