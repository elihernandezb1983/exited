"""Логика тикетов: создание канала, формат имени, кулдаун."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import discord

import config
from core import storage
from .views import APPLICANT_FOOTER_PREFIX, build_ticket_review_view

if TYPE_CHECKING:
    from discord import Guild, Member

TICKET_COOLDOWN_SECONDS = config.TICKET_COOLDOWN_DAYS * 86400


def ticket_channel_name(number: int) -> str:
    return f"ticket-{number:04d}"


def _cooldowns(guild_id: int) -> dict[str, int]:
    return dict(storage.get_guild(guild_id).get("ticket_cooldowns") or {})


def format_cooldown_remaining(seconds: int) -> str:
    days, rem = divmod(max(0, seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} д.")
    if hours:
        parts.append(f"{hours} ч.")
    if minutes or not parts:
        parts.append(f"{minutes} мин.")
    return " ".join(parts)


def get_ticket_cooldown_remaining(guild_id: int, user_id: int) -> int | None:
    """Секунд до конца кулдауна или None, если кулдауна нет."""
    expires_at = _cooldowns(guild_id).get(str(user_id))
    if not expires_at:
        return None
    remaining = int(expires_at - time.time())
    if remaining <= 0:
        return None
    return remaining


def set_ticket_cooldown(guild_id: int, user_id: int) -> None:
    expires_at = int(time.time()) + TICKET_COOLDOWN_SECONDS

    def _mutate(guild: dict) -> None:
        cds = dict(guild.get("ticket_cooldowns") or {})
        cds[str(user_id)] = expires_at
        guild["ticket_cooldowns"] = cds

    storage.mutate_guild(guild_id, _mutate)


def clear_ticket_cooldown(guild_id: int, user_id: int) -> bool:
    removed = False

    def _mutate(guild: dict) -> None:
        nonlocal removed
        cds = dict(guild.get("ticket_cooldowns") or {})
        if str(user_id) in cds:
            del cds[str(user_id)]
            guild["ticket_cooldowns"] = cds
            removed = True

    storage.mutate_guild(guild_id, _mutate)
    return removed


def validate_ticket_settings(guild_id: int) -> None:
    """Проверить настройки до выдачи номера тикета."""
    settings = storage.get_guild(guild_id)
    if not settings.get("ticket_category_id"):
        raise ValueError("no_category")
    if not settings.get("staff_role_ids"):
        raise ValueError("no_staff_roles")


def resolve_next_ticket_number(guild: dict) -> int:
    """Следующий номер тикета (не меньше 1)."""
    raw = guild.get("next_ticket_number")
    try:
        number = int(raw)
    except (TypeError, ValueError):
        number = 1
    return max(1, number)


def allocate_ticket_number(guild_id: int) -> int:
    """Выдать следующий номер тикета."""
    issued: list[int] = []

    def _mutate(guild: dict) -> None:
        number = resolve_next_ticket_number(guild)
        guild["next_ticket_number"] = number + 1
        issued.append(number)

    storage.mutate_guild(guild_id, _mutate)
    return issued[0]


async def create_ticket_channel(
    guild: Guild,
    applicant: Member,
    ticket_number: int,
) -> discord.TextChannel:
    settings = storage.get_guild(guild.id)
    category_id = settings.get("ticket_category_id")
    if not category_id:
        raise ValueError("no_category")

    category = guild.get_channel(category_id)
    if not isinstance(category, discord.CategoryChannel):
        raise ValueError("no_category")

    staff_ids: list[int] = settings.get("staff_role_ids") or []
    if not staff_ids:
        raise ValueError("no_staff_roles")

    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        applicant: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            attach_files=True,
            read_message_history=True,
        ),
    }

    me = guild.me
    if me:
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            manage_channels=True,
            manage_messages=True,
            manage_roles=True,
        )

    for role_id in staff_ids:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            )

    channel = await guild.create_text_channel(
        name=ticket_channel_name(ticket_number),
        category=category,
        overwrites=overwrites,
        reason=f"Заявка в семью от {applicant} (#{ticket_number})",
    )
    return channel


async def send_ticket_opening(
    channel: discord.TextChannel,
    applicant: Member,
    ticket_number: int,
    values: dict[str, str],
) -> None:
    embed = discord.Embed(
        title=config.MESSAGES["ticket_embed_title"].format(number=ticket_number),
        color=config.EMBED_COLOR,
    )
    embed.set_author(
        name=str(applicant),
        icon_url=applicant.display_avatar.url,
    )
    embed.add_field(name="Заявитель", value=applicant.mention, inline=False)
    for field in config.APPLICATION_MODAL["fields"]:
        fid = field["id"]
        embed.add_field(
            name=field["label"],
            value=values.get(fid, "—")[:1024],
            inline=False,
        )
    embed.set_footer(text=f"{APPLICANT_FOOTER_PREFIX}{applicant.id}")

    await channel.send(
        content=f"{applicant.mention} — {config.MESSAGES['ticket_welcome']}",
        embed=embed,
    )

    view = build_ticket_review_view()
    await channel.send(
        content=config.MESSAGES["ticket_review_prompt"],
        view=view,
    )
