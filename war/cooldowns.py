"""Панель кулдаунов атаки/защиты (Components V2)."""

from __future__ import annotations

import time
from typing import Any

import discord
from discord import ui

import config

CD_ACCENT = config.EMBED_COLOR


def _default_cd_state() -> dict[str, Any]:
    return {
        "attack_until": None,
        "defense_until": None,
        "message_id": None,
        "channel_id": None,
    }


def get_cd_state(war: dict[str, Any]) -> dict[str, Any]:
    raw = war.get("cooldowns")
    if not isinstance(raw, dict):
        raw = {}
    merged = _default_cd_state()
    merged.update(raw)
    return merged


def _is_active(until: float | None) -> bool:
    return bool(until and time.time() < until)


def format_remaining(until: float) -> str:
    """Остаток КД: «2ч 59 мин», «1ч 30 мин», «45 мин»."""
    secs = max(0, int(until - time.time()))
    hours, rem = divmod(secs, 3600)
    minutes = rem // 60
    if hours and minutes:
        return f"{hours}ч {minutes} мин"
    if hours:
        return f"{hours}ч"
    return f"{minutes} мин"


def _format_line(
    *,
    emoji: str,
    title: str,
    until: float | None,
) -> str:
    if not _is_active(until):
        return f"{emoji} **{title}**\n> ✅ Можно забивать"

    remaining = format_remaining(until)
    ready_ts = int(until)
    return (
        f"{emoji} **{title}**\n"
        f"> ⏳ **{remaining}**\n"
        f"> готова <t:{ready_ts}:F>"
    )


def _format_cd_label(minutes: int) -> str:
    return f"{minutes} мин"


def build_cooldown_view(
    cd: dict[str, Any],
    *,
    attack_minutes: int,
    defense_minutes: int,
) -> discord.ui.LayoutView:
    attack_text = _format_line(
        emoji="🗡️",
        title="Атака",
        until=cd.get("attack_until"),
    )
    defense_text = _format_line(
        emoji="🛡️",
        title="Защита",
        until=cd.get("defense_until"),
    )

    container = ui.Container(accent_color=discord.Colour(CD_ACCENT))
    container.add_item(ui.TextDisplay("## ⏱ Кулдауны войн"))
    container.add_item(
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    )
    container.add_item(ui.TextDisplay(attack_text))
    container.add_item(
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    )
    container.add_item(ui.TextDisplay(defense_text))
    container.add_item(
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    )
    container.add_item(
        ui.TextDisplay(
            f"> Атака — **{_format_cd_label(attack_minutes)}** · "
            f"Защита — **{_format_cd_label(defense_minutes)}** после забивки",
        ),
    )

    view = ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def any_cd_active(cd: dict[str, Any]) -> bool:
    return _is_active(cd.get("attack_until")) or _is_active(cd.get("defense_until"))
