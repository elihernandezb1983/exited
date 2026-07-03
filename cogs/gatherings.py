from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from audit_log import log_usage_from_interaction
from cogs.panel import _can_use_panel
from gatherings.views import build_gathering_action_view
from gatherings import (
    GatherTimeParseError,
    build_gathering_embed,
    parse_gathering_time,
    save_gathering,
)


class GatheringsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="сбор",
        description="Объявить сбор: МП, время, количество людей и роль для тега",
    )
    @app_commands.describe(
        мп="Что за МП",
        время="15 — через 15 мин; 15:00 или 15 00 — на указанное время",
        люди="Сколько мест в основе",
        роль="Какую роль тегнуть",
        канал="Куда отправить (по умолчанию — текущий)",
    )
    async def gathering(
        self,
        interaction: discord.Interaction,
        мп: str,
        время: str,
        люди: app_commands.Range[int, 1, 99],
        роль: discord.Role,
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
                config.MESSAGES["gathering_wrong_channel"],
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Команда доступна только на сервере.",
                ephemeral=True,
            )
            return

        mp = мп.strip()
        if not mp:
            await interaction.response.send_message(
                config.MESSAGES["gathering_need_mp"],
                ephemeral=True,
            )
            return

        try:
            mode, ends_at, time_hint = parse_gathering_time(время)
        except GatherTimeParseError:
            await interaction.response.send_message(
                config.MESSAGES["gathering_invalid_time"],
                ephemeral=True,
            )
            return

        gathering_data = {
            "creator_id": interaction.user.id,
            "creator_name": interaction.user.display_name,
            "channel_id": target.id,
            "mp": mp,
            "mode": mode,
            "ends_at": ends_at,
            "time_hint": time_hint,
            "people_count": люди,
            "role_id": роль.id,
            "main": [],
            "reserve": [],
            "published": False,
        }
        embed = build_gathering_embed(interaction.guild, gathering_data)
        view = build_gathering_action_view()

        await interaction.response.defer(ephemeral=True)

        try:
            message = await target.send(
                content=config.MESSAGES["gathering_ping"].format(
                    role=роль.mention,
                    mp=mp,
                ),
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                config.MESSAGES["gathering_send_failed"],
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                config.MESSAGES["gathering_send_failed"],
                ephemeral=True,
            )
            return

        save_gathering(interaction.guild.id, message.id, gathering_data)

        log_usage_from_interaction(
            interaction,
            "gathering.created",
            details={
                "mp": mp,
                "mode": mode,
                "people_count": люди,
                "role_id": роль.id,
                "role_name": роль.name,
                "channel_id": target.id,
                "message_id": message.id,
                "ends_at": ends_at,
            },
            bot=self.bot,  # type: ignore[arg-type]
        )

        await interaction.followup.send(
            config.MESSAGES["gathering_posted"].format(
                channel=target.mention,
                jump_url=message.jump_url,
            ),
            ephemeral=True,
        )
