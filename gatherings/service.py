"""Сборы: хранение, парсинг времени и embed."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable, Literal

import discord

import config
from core import storage

if TYPE_CHECKING:
    from discord import Guild

GatherMode = Literal["timer", "clock"]


class GatherTimeParseError(ValueError):
    """Некорректный формат времени сбора."""


def _records(guild_id: int) -> dict[str, dict]:
    return dict(storage.get_guild(guild_id).get("gatherings_by_message") or {})


def get_gathering(guild_id: int, message_id: int) -> dict | None:
    data = _records(guild_id).get(str(message_id))
    return dict(data) if data else None


def save_gathering(guild_id: int, message_id: int, data: dict) -> None:
    def _mutate(guild: dict) -> None:
        records = dict(guild.get("gatherings_by_message") or {})
        records[str(message_id)] = data
        guild["gatherings_by_message"] = records

    storage.mutate_guild(guild_id, _mutate)


def mutate_gathering(
    guild_id: int,
    message_id: int,
    mutator: Callable[[dict], None],
) -> dict | None:
    result: dict | None = None

    def _mutate(guild: dict) -> None:
        nonlocal result
        records = dict(guild.get("gatherings_by_message") or {})
        key = str(message_id)
        if key not in records:
            return
        record = dict(records[key])
        mutator(record)
        records[key] = record
        guild["gatherings_by_message"] = records
        result = record

    storage.mutate_guild(guild_id, _mutate)
    return result


def is_gathering_published(data: dict) -> bool:
    return bool(data.get("published"))


def main_limit(data: dict) -> int:
    return int(data["people_count"])


def main_ids(data: dict) -> list[int]:
    return list(data.get("main") or [])


def reserve_ids(data: dict) -> list[int]:
    return list(data.get("reserve") or [])


def _member_mention(guild: Guild, user_id: int) -> str:
    member = guild.get_member(user_id)
    return member.mention if member else f"<@{user_id}>"


def format_roster(guild: Guild, user_ids: list[int]) -> str:
    if not user_ids:
        return "—"
    return ", ".join(_member_mention(guild, uid) for uid in user_ids)


def parse_gathering_time(raw: str) -> tuple[GatherMode, int, str]:
    text = raw.strip()
    if not text:
        raise GatherTimeParseError()

    clock_match = re.match(r"^(\d{1,2})\s*[:\-\s]\s*(\d{2})$", text)
    if clock_match:
        hour = int(clock_match.group(1))
        minute = int(clock_match.group(2))
        if hour > 23 or minute > 59:
            raise GatherTimeParseError()
        now = datetime.now().astimezone()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return ("clock", int(target.timestamp()), f"{hour:02d}:{minute:02d}")

    if re.fullmatch(r"\d+", text):
        minutes = int(text)
        if minutes < 1 or minutes > 999:
            raise GatherTimeParseError()
        target = datetime.now().astimezone() + timedelta(minutes=minutes)
        return ("timer", int(target.timestamp()), f"{minutes} мин")

    raise GatherTimeParseError()


def format_time_field(mode: GatherMode, ends_at: int, hint: str) -> str:
    if mode == "timer":
        return (
            f"⏳ Через **{hint}** · <t:{ends_at}:R>\n"
            f"> Готовность: <t:{ends_at}:t> (<t:{ends_at}:F>)"
        )
    return (
        f"🕐 **{hint}** · <t:{ends_at}:R>\n"
        f"> <t:{ends_at}:F> · <t:{ends_at}:t>"
    )


def build_gathering_embed(guild: Guild, data: dict) -> discord.Embed:
    main = main_ids(data)
    reserve = reserve_ids(data)
    limit = main_limit(data)
    mode: GatherMode = data["mode"]
    ends_at = int(data["ends_at"])
    time_hint = str(data["time_hint"])

    embed = discord.Embed(
        title="📢 Сбор",
        color=config.EMBED_COLOR,
    )
    embed.add_field(name="МП", value=data["mp"], inline=True)
    embed.add_field(
        name="Время",
        value=format_time_field(mode, ends_at, time_hint),
        inline=False,
    )
    embed.add_field(name="Людей", value=str(limit), inline=True)
    embed.add_field(
        name=f"Основа ({len(main)}/{limit})",
        value=format_roster(guild, main),
        inline=False,
    )
    embed.add_field(
        name=f"Замена ({len(reserve)})",
        value=format_roster(guild, reserve),
        inline=False,
    )

    footer = f"Организатор: {data.get('creator_name') or '—'}"
    if is_gathering_published(data):
        footer += " · Список опубликован"
    embed.set_footer(text=footer)
    return embed
