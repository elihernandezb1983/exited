"""AFK: хранение и список."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core import storage

if TYPE_CHECKING:
    from discord import Guild


def _records(guild_id: int) -> dict[str, dict]:
    return dict(storage.get_guild(guild_id).get("afk_users") or {})


def _save_records(guild_id: int, records: dict[str, dict]) -> None:
    def _mutate(guild: dict) -> None:
        guild["afk_users"] = records

    storage.mutate_guild(guild_id, _mutate)


def purge_expired(guild_id: int) -> None:
    now = time.time()
    records = _records(guild_id)
    changed = False
    for key, record in list(records.items()):
        if int(record.get("until") or 0) <= now:
            del records[key]
            changed = True
    if changed:
        _save_records(guild_id, records)


def get_user_afk(guild_id: int, user_id: int) -> dict | None:
    purge_expired(guild_id)
    record = _records(guild_id).get(str(user_id))
    if not record:
        return None
    if int(record["until"]) <= time.time():
        clear_afk(guild_id, user_id)
        return None
    return dict(record)


def set_afk(guild_id: int, user_id: int, reason: str, minutes: int) -> dict:
    now = int(time.time())
    record = {
        "reason": reason,
        "minutes": minutes,
        "started_at": now,
        "until": now + minutes * 60,
    }

    def _mutate(guild: dict) -> None:
        records = dict(guild.get("afk_users") or {})
        records[str(user_id)] = record
        guild["afk_users"] = records

    storage.mutate_guild(guild_id, _mutate)
    return record


def clear_afk(guild_id: int, user_id: int) -> bool:
    removed = False

    def _mutate(guild: dict) -> None:
        nonlocal removed
        records = dict(guild.get("afk_users") or {})
        if str(user_id) in records:
            del records[str(user_id)]
            guild["afk_users"] = records
            removed = True

    storage.mutate_guild(guild_id, _mutate)
    return removed


def list_active_afk(guild_id: int) -> list[tuple[int, dict]]:
    purge_expired(guild_id)
    items: list[tuple[int, dict]] = []
    for key, record in _records(guild_id).items():
        try:
            user_id = int(key)
        except ValueError:
            continue
        if int(record.get("until") or 0) > time.time():
            items.append((user_id, dict(record)))
    items.sort(key=lambda item: int(item[1]["until"]))
    return items


def _member_mention(guild: Guild, user_id: int) -> str:
    member = guild.get_member(user_id)
    return member.mention if member else f"<@{user_id}>"


def format_afk_list(guild: Guild, guild_id: int) -> str:
    entries = list_active_afk(guild_id)
    if not entries:
        return "—"
    lines: list[str] = []
    for user_id, record in entries:
        until = int(record["until"])
        reason = record.get("reason") or "—"
        lines.append(
            f"{_member_mention(guild, user_id)} — **{reason}**\n"
            f"> до <t:{until}:F> · <t:{until}:R>"
        )
    return "\n\n".join(lines)
