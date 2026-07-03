from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import config
from core import storage
from audit_log import log_moderation, log_usage_from_interaction
from cogs.panel import _can_use_panel


def _channel_line(guild: discord.Guild, channel_id: int | None) -> str:
    if not channel_id:
        return "— (не задан)"
    ch = guild.get_channel(channel_id)
    return ch.mention if isinstance(ch, discord.TextChannel) else f"`{channel_id}`"


def _member_name(member: discord.abc.User | discord.Member | None) -> str | None:
    if member is None:
        return None
    return str(member)


async def _recent_audit_entry(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    *,
    target_id: int | None = None,
    max_age_seconds: float = 5.0,
) -> discord.AuditLogEntry | None:
    try:
        now = datetime.now(timezone.utc)
        async for entry in guild.audit_logs(limit=6, action=action):
            if target_id is not None:
                entry_target = entry.target
                entry_target_id = getattr(entry_target, "id", None)
                if entry_target_id != target_id:
                    continue
            created = entry.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if (now - created).total_seconds() > max_age_seconds:
                continue
            return entry
    except (discord.Forbidden, discord.HTTPException):
        return None
    return None


class AuditCog(commands.Cog):
    """Логи бота (команды) и логи модерации (мут, move и т.д.)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _deny(self, interaction: discord.Interaction) -> bool:
        if _can_use_panel(interaction):
            return False
        await interaction.response.send_message(
            config.MESSAGES["no_permission"],
            ephemeral=True,
        )
        return True

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command,
    ) -> None:
        options: dict[str, str] = {}
        if interaction.namespace:
            for name, value in vars(interaction.namespace).items():
                if value is None:
                    continue
                if isinstance(value, discord.abc.Snowflake):
                    options[name] = str(value.id)
                elif hasattr(value, "value"):
                    options[name] = str(getattr(value, "value"))
                else:
                    options[name] = str(value)

        log_usage_from_interaction(
            interaction,
            f"command.{command.name}",
            details=options or None,
            bot=self.bot,  # type: ignore[arg-type]
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        guild = member.guild
        bot = self.bot

        if before.channel != after.channel:
            if before.channel and after.channel:
                entry = await _recent_audit_entry(
                    guild,
                    discord.AuditLogAction.member_move,
                    target_id=member.id,
                )
                if entry and entry.user.id != member.id:
                    log_moderation(
                        "mod.voice.move",
                        guild_id=guild.id,
                        actor_id=entry.user.id,
                        actor_name=str(entry.user),
                        target_id=member.id,
                        target_name=str(member),
                        details={
                            "from_channel_id": before.channel.id,
                            "from_channel_name": before.channel.name,
                            "to_channel_id": after.channel.id,
                            "to_channel_name": after.channel.name,
                            "reason": entry.reason,
                        },
                        bot=bot,  # type: ignore[arg-type]
                    )
            elif before.channel and after.channel is None:
                entry = await _recent_audit_entry(
                    guild,
                    discord.AuditLogAction.member_disconnect,
                    target_id=member.id,
                )
                if entry and entry.user.id != member.id:
                    log_moderation(
                        "mod.voice.disconnect",
                        guild_id=guild.id,
                        actor_id=entry.user.id,
                        actor_name=str(entry.user),
                        target_id=member.id,
                        target_name=str(member),
                        details={
                            "channel_id": before.channel.id,
                            "channel_name": before.channel.name,
                            "reason": entry.reason,
                        },
                        bot=bot,  # type: ignore[arg-type]
                    )

        if before.mute != after.mute:
            entry = await _recent_audit_entry(
                guild,
                discord.AuditLogAction.member_update,
                target_id=member.id,
            )
            if entry and entry.user.id != member.id:
                log_moderation(
                    "mod.voice.server_mute" if after.mute else "mod.voice.server_unmute",
                    guild_id=guild.id,
                    actor_id=entry.user.id,
                    actor_name=str(entry.user),
                    target_id=member.id,
                    target_name=str(member),
                    details={
                        "channel_id": (after.channel or before.channel).id
                        if (after.channel or before.channel)
                        else None,
                        "channel_name": (after.channel or before.channel).name
                        if (after.channel or before.channel)
                        else None,
                        "reason": entry.reason,
                    },
                    bot=bot,  # type: ignore[arg-type]
                )

        if before.deaf != after.deaf:
            entry = await _recent_audit_entry(
                guild,
                discord.AuditLogAction.member_update,
                target_id=member.id,
            )
            if entry and entry.user.id != member.id:
                log_moderation(
                    "mod.voice.server_deaf" if after.deaf else "mod.voice.server_undeaf",
                    guild_id=guild.id,
                    actor_id=entry.user.id,
                    actor_name=str(entry.user),
                    target_id=member.id,
                    target_name=str(member),
                    details={
                        "channel_id": (after.channel or before.channel).id
                        if (after.channel or before.channel)
                        else None,
                        "channel_name": (after.channel or before.channel).name
                        if (after.channel or before.channel)
                        else None,
                        "reason": entry.reason,
                    },
                    bot=bot,  # type: ignore[arg-type]
                )

    @commands.Cog.listener()
    async def on_member_update(
        self,
        before: discord.Member,
        after: discord.Member,
    ) -> None:
        guild = after.guild
        bot = self.bot

        if before.timed_out_until != after.timed_out_until:
            entry = await _recent_audit_entry(
                guild,
                discord.AuditLogAction.member_update,
                target_id=after.id,
            )
            actor_id = entry.user.id if entry else None
            actor_name = str(entry.user) if entry else None
            reason = entry.reason if entry else None

            if after.timed_out_until:
                until = int(after.timed_out_until.timestamp())
                log_moderation(
                    "mod.timeout.set",
                    guild_id=guild.id,
                    actor_id=actor_id,
                    actor_name=actor_name,
                    target_id=after.id,
                    target_name=str(after),
                    details={
                        "until": f"<t:{until}:F> · <t:{until}:R>",
                        "reason": reason,
                    },
                    bot=bot,  # type: ignore[arg-type]
                )
            elif before.timed_out_until:
                log_moderation(
                    "mod.timeout.remove",
                    guild_id=guild.id,
                    actor_id=actor_id,
                    actor_name=actor_name,
                    target_id=after.id,
                    target_name=str(after),
                    details={"reason": reason},
                    bot=bot,  # type: ignore[arg-type]
                )

        added_roles = set(after.roles) - set(before.roles)
        removed_roles = set(before.roles) - set(after.roles)
        if not added_roles and not removed_roles:
            return

        entry = await _recent_audit_entry(
            guild,
            discord.AuditLogAction.member_role_update,
            target_id=after.id,
        )
        if not entry:
            return

        actor_id = entry.user.id
        actor_name = str(entry.user)
        reason = entry.reason

        for role in added_roles:
            if role.is_default():
                continue
            log_moderation(
                "mod.role.add",
                guild_id=guild.id,
                actor_id=actor_id,
                actor_name=actor_name,
                target_id=after.id,
                target_name=str(after),
                details={
                    "role_id": role.id,
                    "role_name": role.name,
                    "reason": reason,
                },
                bot=bot,  # type: ignore[arg-type]
            )

        for role in removed_roles:
            if role.is_default():
                continue
            log_moderation(
                "mod.role.remove",
                guild_id=guild.id,
                actor_id=actor_id,
                actor_name=actor_name,
                target_id=after.id,
                target_name=str(after),
                details={
                    "role_id": role.id,
                    "role_name": role.name,
                    "reason": reason,
                },
                bot=bot,  # type: ignore[arg-type]
            )

    @commands.Cog.listener()
    async def on_member_ban(
        self,
        guild: discord.Guild,
        user: discord.User | discord.Member,
    ) -> None:
        entry = await _recent_audit_entry(
            guild,
            discord.AuditLogAction.ban,
            target_id=user.id,
        )
        log_moderation(
            "mod.ban",
            guild_id=guild.id,
            actor_id=entry.user.id if entry else None,
            actor_name=str(entry.user) if entry else None,
            target_id=user.id,
            target_name=_member_name(user),
            details={"reason": entry.reason if entry else None},
            bot=self.bot,  # type: ignore[arg-type]
        )

    @commands.Cog.listener()
    async def on_member_unban(
        self,
        guild: discord.Guild,
        user: discord.User,
    ) -> None:
        entry = await _recent_audit_entry(
            guild,
            discord.AuditLogAction.unban,
            target_id=user.id,
        )
        log_moderation(
            "mod.unban",
            guild_id=guild.id,
            actor_id=entry.user.id if entry else None,
            actor_name=str(entry.user) if entry else None,
            target_id=user.id,
            target_name=_member_name(user),
            details={"reason": entry.reason if entry else None},
            bot=self.bot,  # type: ignore[arg-type]
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        entry = await _recent_audit_entry(
            member.guild,
            discord.AuditLogAction.kick,
            target_id=member.id,
        )
        if not entry:
            return
        log_moderation(
            "mod.kick",
            guild_id=member.guild.id,
            actor_id=entry.user.id,
            actor_name=str(entry.user),
            target_id=member.id,
            target_name=str(member),
            details={"reason": entry.reason},
            bot=self.bot,  # type: ignore[arg-type]
        )

    @app_commands.command(
        name="лог-настройка",
        description="Каналы логов модерации и использования бота",
    )
    @app_commands.describe(
        действие="Что настроить",
        канал="Текстовый канал (для каналов логов)",
    )
    @app_commands.choices(
        действие=[
            app_commands.Choice(name="Логи (мут, move, роли…)", value="actions"),
            app_commands.Choice(name="Логи бота (команды)", value="usage"),
            app_commands.Choice(name="Включить логи", value="enable"),
            app_commands.Choice(name="Выключить логи", value="disable"),
            app_commands.Choice(name="Показать все настройки", value="list"),
        ],
    )
    async def log_setup(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
        канал: discord.TextChannel | None = None,
    ) -> None:
        if await self._deny(interaction):
            return
        if not interaction.guild:
            return

        action = действие.value
        guild_id = interaction.guild.id

        if action == "actions":
            if канал is None:
                await interaction.response.send_message(
                    config.MESSAGES["log_setup_need_channel"],
                    ephemeral=True,
                )
                return
            storage.update_guild(guild_id, log_actions_channel_id=канал.id)
            log_usage_from_interaction(
                interaction,
                "log.settings.actions_channel",
                details={"channel_id": канал.id, "channel_name": канал.name},
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.response.send_message(
                config.MESSAGES["log_actions_channel_set"].format(channel=канал.mention),
                ephemeral=True,
            )
            return

        if action == "usage":
            if канал is None:
                await interaction.response.send_message(
                    config.MESSAGES["log_setup_need_channel"],
                    ephemeral=True,
                )
                return
            storage.update_guild(guild_id, log_usage_channel_id=канал.id)
            log_usage_from_interaction(
                interaction,
                "log.settings.usage_channel",
                details={"channel_id": канал.id, "channel_name": канал.name},
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.response.send_message(
                config.MESSAGES["log_usage_channel_set"].format(channel=канал.mention),
                ephemeral=True,
            )
            return

        if action == "enable":
            storage.update_guild(guild_id, audit_log_enabled=True)
            log_usage_from_interaction(
                interaction,
                "log.settings.enabled",
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.response.send_message(
                config.MESSAGES["log_enabled"],
                ephemeral=True,
            )
            return

        if action == "disable":
            log_usage_from_interaction(
                interaction,
                "log.settings.disabled",
                bot=self.bot,  # type: ignore[arg-type]
            )
            storage.update_guild(guild_id, audit_log_enabled=False)
            await interaction.response.send_message(
                config.MESSAGES["log_disabled"],
                ephemeral=True,
            )
            return

        guild_data = storage.get_guild(guild_id)
        enabled = guild_data.get("audit_log_enabled", True)
        status = "✅ включено" if enabled else "⛔ выключено"
        await interaction.response.send_message(
            config.MESSAGES["log_settings_summary"].format(
                status=status,
                actions=_channel_line(
                    interaction.guild,
                    guild_data.get("log_actions_channel_id"),
                ),
                usage=_channel_line(
                    interaction.guild,
                    guild_data.get("log_usage_channel_id"),
                ),
            ),
            ephemeral=True,
        )
