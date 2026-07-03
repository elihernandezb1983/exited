from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
import tickets
from audit_log import log_usage_from_interaction
from core import storage
from core.permissions import can_manage_access


def _format_roles(guild: discord.Guild, role_ids: list[int]) -> str:
    if not role_ids:
        return "— (роли не заданы)"
    lines = []
    for rid in role_ids:
        role = guild.get_role(rid)
        lines.append(role.mention if role else f"`{rid}` (удалена)")
    return "\n".join(lines)


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _deny(self, interaction: discord.Interaction) -> bool:
        if can_manage_access(interaction):
            return False
        await interaction.response.send_message(
            config.MESSAGES["access_manage_denied"],
            ephemeral=True,
        )
        return True

    async def _change_staff_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        *,
        add: bool,
    ) -> None:
        guild_data = storage.get_guild(interaction.guild.id)  # type: ignore[union-attr]
        ids: list[int] = list(guild_data.get("staff_role_ids") or [])

        if add:
            if role.id in ids:
                await interaction.response.send_message(
                    config.MESSAGES["access_ticket_exists"].format(role=role.mention),
                    ephemeral=True,
                )
                return
            ids.append(role.id)
            log_kind = "access.ticket.add"
            done_msg = config.MESSAGES["access_ticket_added"]
        else:
            if role.id not in ids:
                await interaction.response.send_message(
                    config.MESSAGES["access_ticket_missing"].format(role=role.mention),
                    ephemeral=True,
                )
                return
            ids.remove(role.id)
            log_kind = "access.ticket.remove"
            done_msg = config.MESSAGES["access_ticket_removed"]

        storage.update_guild(interaction.guild.id, staff_role_ids=ids)  # type: ignore[union-attr]
        log_usage_from_interaction(
            interaction,
            log_kind,
            details={"role_id": role.id, "role_name": role.name},
            bot=self.bot,  # type: ignore[arg-type]
        )
        await interaction.response.send_message(
            done_msg.format(role=role.mention),
            ephemeral=True,
        )

    @app_commands.command(
        name="тикет-настройка",
        description="Настройка тикетов заявок в семью",
    )
    @app_commands.describe(
        действие="Что сделать",
        категория="Категория для каналов ticket-0001",
        роль="Роль (доступ к тикетам или при принятии)",
        пользователь="У кого снять кулдаун (для «Снять кулдаун»)",
    )
    @app_commands.choices(
        действие=[
            app_commands.Choice(
                name="Категория для тикетов",
                value="category",
            ),
            app_commands.Choice(
                name="Доступ к тикетам — добавить роль",
                value="staff_add",
            ),
            app_commands.Choice(
                name="Доступ к тикетам — удалить роль",
                value="staff_remove",
            ),
            app_commands.Choice(
                name="Роль при принятии заявки",
                value="accepted",
            ),
            app_commands.Choice(
                name="Снять кулдаун на заявку",
                value="clear_cooldown",
            ),
            app_commands.Choice(
                name="Показать все настройки",
                value="list",
            ),
        ],
    )
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
        категория: discord.CategoryChannel | None = None,
        роль: discord.Role | None = None,
        пользователь: discord.Member | None = None,
    ) -> None:
        if await self._deny(interaction):
            return
        if not interaction.guild:
            return

        action = действие.value

        if action == "category":
            if категория is None:
                await interaction.response.send_message(
                    config.MESSAGES["ticket_setup_need_category"],
                    ephemeral=True,
                )
                return
            storage.update_guild(
                interaction.guild.id,
                ticket_category_id=категория.id,
            )
            log_usage_from_interaction(
                interaction,
                "ticket.settings.category",
                details={"category_id": категория.id, "category_name": категория.name},
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.response.send_message(
                config.MESSAGES["ticket_category_set"].format(category=категория.mention),
                ephemeral=True,
            )
            return

        if action in ("staff_add", "staff_remove", "accepted"):
            if роль is None:
                await interaction.response.send_message(
                    config.MESSAGES["ticket_setup_need_role"],
                    ephemeral=True,
                )
                return

        if action == "staff_add":
            await self._change_staff_role(interaction, роль, add=True)
            return

        if action == "staff_remove":
            await self._change_staff_role(interaction, роль, add=False)
            return

        if action == "accepted":
            storage.update_guild(interaction.guild.id, accepted_role_id=роль.id)
            log_usage_from_interaction(
                interaction,
                "ticket.settings.accepted_role",
                details={"role_id": роль.id, "role_name": роль.name},
                bot=self.bot,  # type: ignore[arg-type]
            )
            await interaction.response.send_message(
                config.MESSAGES["ticket_accepted_role_set"].format(role=роль.mention),
                ephemeral=True,
            )
            return

        if action == "clear_cooldown":
            target = пользователь or interaction.user
            if tickets.clear_ticket_cooldown(interaction.guild.id, target.id):
                log_usage_from_interaction(
                    interaction,
                    "ticket.cooldown.cleared",
                    details={"target_id": target.id, "target_name": str(target)},
                    bot=self.bot,  # type: ignore[arg-type]
                )
                await interaction.response.send_message(
                    config.MESSAGES["ticket_cooldown_cleared"].format(user=target.mention),
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                config.MESSAGES["ticket_cooldown_not_set"].format(user=target.mention),
                ephemeral=True,
            )
            return

        # list
        guild_data = storage.get_guild(interaction.guild.id)
        category_id = guild_data.get("ticket_category_id")
        category = (
            interaction.guild.get_channel(category_id)
            if category_id
            else None
        )
        cat_text = (
            category.mention
            if isinstance(category, discord.CategoryChannel)
            else "— (не задана)"
        )

        accepted_id = guild_data.get("accepted_role_id")
        accepted_role = (
            interaction.guild.get_role(accepted_id) if accepted_id else None
        )
        accepted_text = accepted_role.mention if accepted_role else "— (не задана)"

        await interaction.response.send_message(
            config.MESSAGES["ticket_settings_summary"].format(
                category=cat_text,
                roles=_format_roles(
                    interaction.guild,
                    guild_data.get("staff_role_ids") or [],
                ),
                accepted_role=accepted_text,
                next_number=tickets.resolve_next_ticket_number(guild_data),
            ),
            ephemeral=True,
        )
