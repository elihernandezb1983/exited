from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from audit_log import log_usage_from_interaction
from panels import build_panel
from core.permissions import can_use_panel


def _can_use_panel(interaction: discord.Interaction) -> bool:
    return can_use_panel(interaction)


class PanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="панель",
        description="Отправить панель в выбранный канал",
    )
    @app_commands.describe(
        панель="Какую панель отправить",
        канал="Куда отправить (по умолчанию — текущий)",
    )
    @app_commands.choices(
        панель=[
            app_commands.Choice(name=cfg["label"], value=panel_id)
            for panel_id, cfg in config.PANELS.items()
        ],
    )
    async def panel(
        self,
        interaction: discord.Interaction,
        панель: app_commands.Choice[str],
        канал: discord.TextChannel | None = None,
    ) -> None:
        if not _can_use_panel(interaction):
            await interaction.response.send_message(
                config.MESSAGES["no_permission"],
                ephemeral=True,
            )
            return

        target = канал or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                "Укажите текстовый канал для отправки панели.",
                ephemeral=True,
            )
            return

        panel_id = панель.value
        panel_cfg = config.PANELS[panel_id]

        try:
            view, files, warning = build_panel(panel_id)
        except KeyError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await target.send(view=view, files=files or None)

        log_usage_from_interaction(
            interaction,
            "panel.sent",
            details={
                "panel": panel_id,
                "panel_label": panel_cfg["label"],
                "channel_id": target.id,
                "channel_name": target.name,
            },
            bot=self.bot,  # type: ignore[arg-type]
        )

        reply = config.MESSAGES["panel_sent"].format(
            panel=panel_cfg["label"],
            channel=target.mention,
        )
        if warning:
            reply += f"\n\n⚠ {warning}"

        await interaction.response.send_message(reply, ephemeral=True)
