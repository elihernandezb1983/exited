"""Состояние войн на сервере (guilds.json)."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

import config
from core import storage
from core.console_log import detail
from war.cooldowns import _default_cd_state

log = logging.getLogger(__name__)


def _default_war() -> dict[str, Any]:
    return {
        "last_declare": None,
        "pending_by_location": {},
        "pending_report": None,
        "ping_role_ids": [],
        "attack_cd_minutes": config.WAR_ATTACK_CD_MINUTES,
        "defense_cd_minutes": config.WAR_DEFENSE_CD_MINUTES,
        "cooldowns": _default_cd_state(),
    }


def _merge_war(raw: Any) -> dict[str, Any]:
    merged = _default_war()
    if isinstance(raw, dict):
        merged.update(raw)
    if not isinstance(merged.get("cooldowns"), dict):
        merged["cooldowns"] = _default_cd_state()
    else:
        cd = _default_cd_state()
        cd.update(merged["cooldowns"])
        merged["cooldowns"] = cd
    return merged


def _env_cd_minutes(kind: str) -> int | None:
    prefix = kind.upper()
    for key, mult in (
        (f"WAR_{prefix}_CD_SEC", 1 / 60),
        (f"WAR_{prefix}_CD_MINUTES", 1),
        (f"WAR_{prefix}_CD_HOURS", 60),
    ):
        raw = os.getenv(key, "")
        if not raw:
            continue
        try:
            return max(1, int(float(raw) * mult))
        except ValueError:
            continue
    return None


def _read_cd_minutes(war: dict[str, Any], kind: str) -> int:
    key = f"{kind}_cd_minutes"
    raw = war.get(key)
    if isinstance(raw, (int, float)) and raw > 0:
        return int(raw)
    old = war.get(f"{kind}_cd_hours")
    if isinstance(old, (int, float)) and old > 0:
        return int(old) * 60
    env = _env_cd_minutes(kind)
    if env is not None:
        return env
    if kind == "attack":
        return config.WAR_ATTACK_CD_MINUTES
    return config.WAR_DEFENSE_CD_MINUTES


def get_attack_cd_minutes(war: dict[str, Any]) -> int:
    return _read_cd_minutes(war, "attack")


def get_defense_cd_minutes(war: dict[str, Any]) -> int:
    return _read_cd_minutes(war, "defense")


def get_war_state(guild_id: int) -> dict[str, Any]:
    guild = storage.get_guild(guild_id)
    war = guild.get("war")
    if not isinstance(war, dict):
        war = _default_war()
        storage.update_guild(guild_id, war=war)
        return _merge_war(war)
    return _merge_war(war)


def mutate_war(guild_id: int, mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Атомарное изменение состояния войн на сервере."""

    def _mutate(guild: dict[str, Any]) -> None:
        war = _merge_war(guild.get("war"))
        mutator(war)
        guild["war"] = war

    storage.mutate_guild(guild_id, _mutate)
    return get_war_state(guild_id)


def save_war(guild_id: int, war: dict[str, Any]) -> None:
    storage.update_guild(guild_id, war=_merge_war(war))


def _explicit_guild_id() -> int | None:
    raw = os.getenv("GUILD_ID", "") or (
        str(config.SYNC_GUILD_ID) if config.SYNC_GUILD_ID else ""
    )
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return None


def resolve_war_guild_ids() -> list[int]:
    """Серверы для обработки TG-событий: GUILD_ID или все с настроенным war_channel_id."""
    explicit = _explicit_guild_id()
    if explicit:
        return [explicit]

    ids: list[int] = []
    for key, guild in storage.get_all_guilds().items():
        if guild.get("war_channel_id"):
            ids.append(int(key))

    if len(ids) > 1:
        detail(
            f"войны: GUILD_ID не задан — события пойдут на {len(ids)} сервер(а): {ids}",
        )
    return ids


def resolve_guild_id() -> int | None:
    """Первый сервер для войн (обратная совместимость)."""
    ids = resolve_war_guild_ids()
    return ids[0] if ids else None
