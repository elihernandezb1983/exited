"""Discord embed: противник, формат, время, исход."""

from __future__ import annotations

import discord

import config

from war.parser import WarEvent, WarEventKind

OUTCOME_PENDING = "ожидается"
WAR_EMBED_COLOR = config.EMBED_COLOR


def _field_value(text: str) -> str:
    return f"> {text or '—'}"


def player_outcome(declare: WarEvent, outcome: WarEvent) -> str:
    """Только Win или Lose с точки зрения вашей организации."""
    if outcome.kind == WarEventKind.LOSS:
        return "Lose"

    if outcome.kind == WarEventKind.DEFENSE_WIN:
        return "Win" if declare.kind == WarEventKind.DEFENSE_DECLARE else "Lose"

    if outcome.kind == WarEventKind.ATTACK_WIN:
        return "Win" if declare.kind == WarEventKind.ATTACK_DECLARE else "Lose"

    return "—"


def declare_title(kind: WarEventKind) -> str:
    if kind == WarEventKind.DEFENSE_DECLARE:
        return "❌ Вам забили войну"
    if kind == WarEventKind.ATTACK_DECLARE:
        return "✅ Вы забили войну"
    return "⚔️ Война"


def build_war_embed(
    declare: WarEvent,
    *,
    outcome: WarEvent | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=declare_title(declare.kind),
        color=WAR_EMBED_COLOR,
    )

    embed.add_field(
        name="Противник",
        value=_field_value(declare.opponent or "—"),
        inline=False,
    )
    embed.add_field(
        name="Сколько на сколько",
        value=_field_value(declare.format or "—"),
        inline=False,
    )
    embed.add_field(
        name="На какое время",
        value=_field_value(declare.time or "—"),
        inline=False,
    )

    outcome_text = (
        player_outcome(declare, outcome) if outcome else OUTCOME_PENDING
    )
    embed.add_field(
        name="Исход",
        value=_field_value(outcome_text),
        inline=False,
    )

    if outcome and outcome.battle_id:
        loc = declare.location or outcome.location
        footer = f"Бой #{outcome.battle_id}"
        if loc:
            footer = f"{loc} · {footer}"
        embed.set_footer(text=footer)
    elif declare.location:
        embed.set_footer(text=declare.location)

    return embed
