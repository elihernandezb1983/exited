"""Контракты: хранение состояния и embed."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

import discord

import config
from core import storage

if TYPE_CHECKING:
    from discord import Guild

CONTRACT_FOOTER_PREFIX = "contract:"


def _contracts(guild_id: int) -> dict[str, dict]:
    return dict(storage.get_guild(guild_id).get("contracts_by_message") or {})


def get_contract(guild_id: int, message_id: int) -> dict | None:
    data = _contracts(guild_id).get(str(message_id))
    return dict(data) if data else None


def save_contract(guild_id: int, message_id: int, data: dict) -> None:
    def _mutate(guild: dict) -> None:
        records = dict(guild.get("contracts_by_message") or {})
        records[str(message_id)] = data
        guild["contracts_by_message"] = records

    storage.mutate_guild(guild_id, _mutate)


def mutate_contract(
    guild_id: int,
    message_id: int,
    mutator: Callable[[dict], None],
) -> dict | None:
    result: dict | None = None

    def _mutate(guild: dict) -> None:
        nonlocal result
        records = dict(guild.get("contracts_by_message") or {})
        key = str(message_id)
        if key not in records:
            return
        record = dict(records[key])
        mutator(record)
        records[key] = record
        guild["contracts_by_message"] = records
        result = record

    storage.mutate_guild(guild_id, _mutate)
    return result


def slot_count(data: dict) -> int:
    return int(data.get("people_count") or config.CONTRACT_SLOTS)


def is_contract_closed(data: dict) -> bool:
    return bool(data.get("closed"))


def _member_mention(guild: Guild, user_id: int) -> str:
    member = guild.get_member(user_id)
    return member.mention if member else f"<@{user_id}>"


def format_participants(guild: Guild, participant_ids: list[int]) -> str:
    if not participant_ids:
        return "—"
    return ", ".join(_member_mention(guild, uid) for uid in participant_ids)


def participants_mentions(guild: Guild, participant_ids: list[int]) -> str:
    if not participant_ids:
        return ""
    return " ".join(_member_mention(guild, uid) for uid in participant_ids)


def _format_status_timestamp(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone()
        return local.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return ""


def _footer_text(data: dict) -> str:
    participants: list[int] = list(data.get("participants") or [])
    status = data.get("status_label") or "—"
    base = f"Людей: {len(participants)} | Статус: {status}"
    ts = _format_status_timestamp(data.get("status_at"))
    if ts:
        base += f" - {ts}"
    return base


def build_contract_embed(guild: Guild, data: dict) -> discord.Embed:
    participants: list[int] = list(data.get("participants") or [])
    people_count = slot_count(data)
    creator_id = int(data["creator_id"])
    full_percent = str(data.get("full_percent") or "—").lower()

    embed = discord.Embed(
        title=data["name"],
        color=config.EMBED_COLOR,
    )
    embed.add_field(
        name="Автор",
        value=_member_mention(guild, creator_id),
        inline=True,
    )
    embed.add_field(
        name="Контракт",
        value=data["name"],
        inline=True,
    )
    embed.add_field(
        name="На 100%",
        value=full_percent,
        inline=True,
    )
    embed.add_field(
        name=f"Участники ({len(participants)}/{people_count})",
        value=format_participants(guild, participants),
        inline=False,
    )
    embed.set_footer(text=_footer_text(data))
    return embed
