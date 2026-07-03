"""Единое разрешение ID каналов: storage → .env → config."""

from __future__ import annotations

import os

import config
from core import storage


def resolve_channel_id(
    guild_id: int | None,
    *,
    storage_key: str,
    env_key: str,
    config_default: int | None = None,
) -> int | None:
    """Приоритет: настройки сервера → .env → config → первый guild в storage."""
    if guild_id is not None:
        cid = storage.get_guild(guild_id).get(storage_key)
        if cid:
            return int(cid)

    raw = os.getenv(env_key, "")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass

    if config_default:
        return int(config_default)

    for guild in storage.get_all_guilds().values():
        cid = guild.get(storage_key)
        if cid:
            return int(cid)

    return None
