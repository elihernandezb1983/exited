from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from core import storage
from audit_log import log_usage_from_interaction
from cogs.panel import _can_use_panel
from war.state import get_attack_cd_minutes, get_defense_cd_minutes, get_war_state, mutate_war


def _channel_mention(
    guild: discord.Guild,
    channel_id: int | None,
) -> str:
    if not channel_id:
        return "— (не задан)"
    ch = guild.get_channel(channel_id)
    return ch.mention if isinstance(ch, discord.TextChannel) else f"`{channel_id}`"


def _role_mention(guild: discord.Guild, war: dict) -> str:
    ids: list[int] = list(war.get("ping_role_ids") or [])
    if not ids:
        return "— (не задана)"
    role = guild.get_role(ids[0])
    return role.mention if role else f"`{ids[0]}`"


class WarCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        handler = getattr(self.bot, "war_handler", None)
        if handler:
            await handler.on_discord_message(message)

    async def _deny(self, interaction: discord.Interaction) -> bool:
        if _can_use_panel(interaction):
            return False
        await interaction.response.send_message(
            config.MESSAGES["no_permission"],
            ephemeral=True,
        )
        return True

    @app_commands.command(
        name="война-настройка",
        description="Каналы, кулдауны и роль для войн",
    )
    @app_commands.describe(
        действие="Что настроить",
        канал="Текстовый канал (для действий с каналами)",
        роль="Роль (для тега при скрине)",
        минут="Минуты кулдауна (для КД атаки или защиты)",
    )
    @app_commands.choices(
        действие=[
            app_commands.Choice(
                name="Канал статистики (embed)",
                value="stats",
            ),
            app_commands.Choice(
                name="Канал скринов",
                value="screenshots",
            ),
            app_commands.Choice(
                name="Канал кулдаунов",
                value="cooldowns",
            ),
            app_commands.Choice(
                name="КД атаки (минуты)",
                value="cd_attack",
            ),
            app_commands.Choice(
                name="КД защиты (минуты)",
                value="cd_defense",
            ),
            app_commands.Choice(
                name="Роль для тега при скрине",
                value="ping_role",
            ),
            app_commands.Choice(
                name="Показать все настройки",
                value="list",
            ),
        ],
    )
    async def war_setup(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
        канал: discord.TextChannel | None = None,
        роль: discord.Role | None = None,
        минут: app_commands.Range[int, 1, 1440] | None = None,
    ) -> None:
        if await self._deny(interaction):
            return
        if not interaction.guild:
            return

        action = действие.value
        guild_id = interaction.guild.id

        if action == "stats":
            if канал is None:
                await interaction.response.send_message(
                    config.MESSAGES["war_setup_need_channel"],
                    ephemeral=True,
                )
                return
            storage.update_guild(guild_id, war_channel_id=канал.id)
            log_usage_from_interaction(
                interaction,
                "war.settings.stats_channel",
                details={"channel_id": канал.id, "channel_name": канал.name},
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.response.send_message(
                config.MESSAGES["war_channel_set"].format(channel=канал.mention),
                ephemeral=True,
            )
            return

        if action == "screenshots":
            if канал is None:
                await interaction.response.send_message(
                    config.MESSAGES["war_setup_need_channel"],
                    ephemeral=True,
                )
                return
            storage.update_guild(guild_id, war_report_channel_id=канал.id)
            log_usage_from_interaction(
                interaction,
                "war.settings.screenshots_channel",
                details={"channel_id": канал.id, "channel_name": канал.name},
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.response.send_message(
                config.MESSAGES["war_report_channel_set"].format(channel=канал.mention),
                ephemeral=True,
            )
            return

        if action == "cooldowns":
            if канал is None:
                await interaction.response.send_message(
                    config.MESSAGES["war_setup_need_channel"],
                    ephemeral=True,
                )
                return
            handler = getattr(self.bot, "war_handler", None)
            if not handler:
                await interaction.response.send_message(
                    "Обработчик войн не загружен.",
                    ephemeral=True,
                )
                return
            await interaction.response.defer(ephemeral=True)
            await handler.cd_handler.deploy_panel(guild_id, канал)
            log_usage_from_interaction(
                interaction,
                "war.settings.cooldowns_channel",
                details={"channel_id": канал.id, "channel_name": канал.name},
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.followup.send(
                config.MESSAGES["war_cd_channel_set"].format(channel=канал.mention),
                ephemeral=True,
            )
            return

        if action in ("cd_attack", "cd_defense"):
            if минут is None:
                await interaction.response.send_message(
                    config.MESSAGES["war_setup_need_minutes"],
                    ephemeral=True,
                )
                return
            if action == "cd_attack":
                minutes = int(минут)

                def _mutate(w: dict) -> None:
                    w["attack_cd_minutes"] = minutes

                mutate_war(guild_id, _mutate)
                label = "атаки"
            else:
                minutes = int(минут)

                def _mutate(w: dict) -> None:
                    w["defense_cd_minutes"] = minutes

                mutate_war(guild_id, _mutate)
                label = "защиты"

            handler = getattr(self.bot, "war_handler", None)
            if handler:
                await handler.cd_handler.refresh(guild_id)

            log_usage_from_interaction(
                interaction,
                f"war.settings.{action}",
                details={"minutes": int(минут)},
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.response.send_message(
                config.MESSAGES["war_cd_minutes_set"].format(
                    kind=label,
                    minutes=int(минут),
                ),
                ephemeral=True,
            )
            return

        if action == "ping_role":
            if роль is None:
                await interaction.response.send_message(
                    config.MESSAGES["war_setup_need_role"],
                    ephemeral=True,
                )
                return
            role_id = роль.id

            def _mutate(w: dict) -> None:
                w["ping_role_ids"] = [role_id]

            mutate_war(guild_id, _mutate)
            log_usage_from_interaction(
                interaction,
                "war.settings.ping_role",
                details={"role_id": роль.id, "role_name": роль.name},
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.response.send_message(
                config.MESSAGES["war_ping_role_set"].format(role=роль.mention),
                ephemeral=True,
            )
            return

        # list
        guild_data = storage.get_guild(guild_id)
        war = get_war_state(guild_id)
        await interaction.response.send_message(
            config.MESSAGES["war_settings_summary"].format(
                stats=_channel_mention(
                    interaction.guild,
                    guild_data.get("war_channel_id"),
                ),
                screenshots=_channel_mention(
                    interaction.guild,
                    guild_data.get("war_report_channel_id"),
                ),
                cooldowns=_channel_mention(
                    interaction.guild,
                    guild_data.get("war_cd_channel_id"),
                ),
                attack_cd=get_attack_cd_minutes(war),
                defense_cd=get_defense_cd_minutes(war),
                ping_role=_role_mention(interaction.guild, war),
            ),
            ephemeral=True,
        )

