from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from core import storage
from audit_log import log_usage_from_interaction
from core.permissions import can_manage_access


def _format_roles(guild: discord.Guild, role_ids: list[int]) -> str:
    if not role_ids:
        return "— (роли не заданы)"
    lines = []
    for rid in role_ids:
        role = guild.get_role(rid)
        lines.append(role.mention if role else f"`{rid}` (удалена)")
    return "\n".join(lines)


class AccessCog(commands.Cog):
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

    async def _change_roles(
        self,
        interaction: discord.Interaction,
        *,
        field: str,
        role: discord.Role,
        add: bool,
        log_kind: str,
        exists_msg: str,
        missing_msg: str,
        done_msg: str,
    ) -> None:
        guild_data = storage.get_guild(interaction.guild.id)  # type: ignore[union-attr]
        ids: list[int] = list(guild_data.get(field) or [])

        if add:
            if role.id in ids:
                await interaction.response.send_message(
                    exists_msg.format(role=role.mention),
                    ephemeral=True,
                )
                return
            ids.append(role.id)
        else:
            if role.id not in ids:
                await interaction.response.send_message(
                    missing_msg.format(role=role.mention),
                    ephemeral=True,
                )
                return
            ids.remove(role.id)

        storage.update_guild(interaction.guild.id, **{field: ids})  # type: ignore[union-attr]
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
        name="доступ-модератор",
        description="Выдать или убрать роль модератора бота",
    )
    @app_commands.describe(
        действие="Добавить, удалить роль или показать список",
        роль="Роль модератора (для добавления и удаления)",
    )
    @app_commands.choices(
        действие=[
            app_commands.Choice(name="Добавить роль", value="add"),
            app_commands.Choice(name="Удалить роль", value="remove"),
            app_commands.Choice(name="Показать список", value="list"),
        ],
    )
    async def moderator_access(
        self,
        interaction: discord.Interaction,
        действие: app_commands.Choice[str],
        роль: discord.Role | None = None,
    ) -> None:
        if await self._deny(interaction):
            return
        if not interaction.guild:
            return

        action = действие.value
        if action == "list":
            guild_data = storage.get_guild(interaction.guild.id)
            await interaction.response.send_message(
                config.MESSAGES["access_moderator_list"].format(
                    roles=_format_roles(
                        interaction.guild,
                        guild_data.get("moderator_role_ids") or [],
                    ),
                ),
                ephemeral=True,
            )
            return

        if роль is None:
            await interaction.response.send_message(
                config.MESSAGES["access_need_role"],
                ephemeral=True,
            )
            return

        await self._change_roles(
            interaction,
            field="moderator_role_ids",
            role=роль,
            add=action == "add",
            log_kind=(
                "access.moderator.add"
                if action == "add"
                else "access.moderator.remove"
            ),
            exists_msg=config.MESSAGES["access_moderator_exists"],
            missing_msg=config.MESSAGES["access_moderator_missing"],
            done_msg=(
                config.MESSAGES["access_moderator_added"]
                if action == "add"
                else config.MESSAGES["access_moderator_removed"]
            ),
        )
