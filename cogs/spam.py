from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import config
from audit_log import log_usage_from_interaction
from core.permissions import can_moderate


class SpamCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="спам",
        description="Отправить несколько сообщений с тегом роли в канал",
    )
    @app_commands.describe(
        роль="Роль для тега (можно @everyone)",
        сообщение="Текст сообщения",
        количество="Сколько раз отправить (1–25)",
        канал="Куда отправить (по умолчанию — текущий)",
    )
    async def spam(
        self,
        interaction: discord.Interaction,
        роль: discord.Role,
        сообщение: str,
        количество: app_commands.Range[int, 1, 25],
        канал: discord.TextChannel | None = None,
    ) -> None:
        if not can_moderate(interaction):
            await interaction.response.send_message(
                config.MESSAGES["no_permission"],
                ephemeral=True,
            )
            return

        if not interaction.guild:
            await interaction.response.send_message(
                "Команда доступна только на сервере.",
                ephemeral=True,
            )
            return

        target = канал or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                config.MESSAGES["spam_wrong_channel"],
                ephemeral=True,
            )
            return

        text = сообщение.strip()
        if not text:
            await interaction.response.send_message(
                config.MESSAGES["spam_need_message"],
                ephemeral=True,
            )
            return

        me = interaction.guild.me
        if me:
            perms = target.permissions_for(me)
            if not perms.send_messages:
                await interaction.response.send_message(
                    config.MESSAGES["spam_send_failed"],
                    ephemeral=True,
                )
                return
            if роль.is_default() and not perms.mention_everyone:
                await interaction.response.send_message(
                    config.MESSAGES["spam_no_everyone"],
                    ephemeral=True,
                )
                return

        ping_everyone = роль.is_default()
        content = f"{роль.mention} {text}"
        mentions = discord.AllowedMentions(
            roles=not ping_everyone,
            everyone=ping_everyone,
        )

        await interaction.response.defer(ephemeral=True)

        sent = 0
        for _ in range(количество):
            try:
                await target.send(content=content, allowed_mentions=mentions)
                sent += 1
            except discord.Forbidden:
                await interaction.followup.send(
                    config.MESSAGES["spam_send_failed"],
                    ephemeral=True,
                )
                break
            except discord.HTTPException:
                await interaction.followup.send(
                    config.MESSAGES["spam_send_failed"],
                    ephemeral=True,
                )
                break
            if sent < количество:
                await asyncio.sleep(1.1)

        if sent:
            log_usage_from_interaction(
                interaction,
                "spam.sent",
                details={
                    "role_id": роль.id,
                    "role_name": роль.name,
                    "count": sent,
                    "channel_id": target.id,
                    "channel_name": target.name,
                    "message_preview": text[:100],
                },
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.followup.send(
                config.MESSAGES["spam_done"].format(
                    sent=sent,
                    channel=target.mention,
                    role=роль.mention,
                ),
                ephemeral=True,
            )
