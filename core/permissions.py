"""Права: модераторы бота и персонал тикетов."""

from __future__ import annotations

import discord

import config
from core import storage


def _member(interaction: discord.Interaction) -> discord.Member | None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return None
    return interaction.user


def can_manage_access(interaction: discord.Interaction) -> bool:
    """Настройка ролей и серверных параметров бота."""
    member = _member(interaction)
    if not member:
        return False
    if member.guild_permissions.administrator:
        return True
    return member.guild_permissions.manage_guild


def moderator_role_ids(guild_id: int) -> list[int]:
    return list(storage.get_guild(guild_id).get("moderator_role_ids") or [])


def ticket_role_ids(guild_id: int) -> list[int]:
    return list(storage.get_guild(guild_id).get("staff_role_ids") or [])


def can_moderate(interaction: discord.Interaction) -> bool:
    """Панель, сборы, контракты, войны."""
    member = _member(interaction)
    if not member:
        return False
    if member.guild_permissions.administrator:
        return True
    if config.PANEL_ALLOWED_ROLE_IDS and any(
        role.id in config.PANEL_ALLOWED_ROLE_IDS for role in member.roles
    ):
        return True
    mod_ids = moderator_role_ids(member.guild.id)
    return any(role.id in mod_ids for role in member.roles)


def can_use_panel(interaction: discord.Interaction) -> bool:
    return can_moderate(interaction)


def can_review_ticket(interaction: discord.Interaction) -> bool:
    """Просмотр тикетов и кнопки принять/отказать."""
    member = _member(interaction)
    if not member:
        return False
    if member.guild_permissions.administrator:
        return True
    staff_ids = ticket_role_ids(member.guild.id)
    return any(role.id in staff_ids for role in member.roles)
