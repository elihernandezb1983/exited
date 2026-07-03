"""AFK: модалка и обработчики кнопок."""

from __future__ import annotations

import discord
from discord import ui

import config
from afk import service as afk
from audit_log import log_usage_from_interaction

GO_ID = "afk:go"
LEAVE_ID = "afk:leave"
LIST_ID = "afk:list"


def build_afk_list_view(list_text: str) -> ui.LayoutView:
    """Эфемерный список AFK в Components V2."""
    container = ui.Container(accent_color=discord.Colour(config.EMBED_COLOR))
    container.add_item(ui.TextDisplay("### Кто в AFK:"))
    container.add_item(
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    )
    container.add_item(ui.TextDisplay(list_text))
    view = ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def build_afk_list_empty_view() -> ui.LayoutView:
    container = ui.Container(accent_color=discord.Colour(config.EMBED_COLOR))
    container.add_item(ui.TextDisplay(config.MESSAGES["afk_list_empty"]))
    view = ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


class AfkGoModal(ui.Modal, title="Уйти в AFK"):
    reason = ui.TextInput(
        label="Причина",
        placeholder="Например: ушёл на работу",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )
    minutes = ui.TextInput(
        label="На сколько (минут)",
        placeholder="30",
        style=discord.TextStyle.short,
        max_length=4,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Доступно только на сервере.",
                ephemeral=True,
            )
            return

        reason = self.reason.value.strip()
        if not reason:
            await interaction.response.send_message(
                config.MESSAGES["afk_need_reason"],
                ephemeral=True,
            )
            return

        try:
            minutes = int(self.minutes.value.strip())
        except ValueError:
            await interaction.response.send_message(
                config.MESSAGES["afk_invalid_minutes"],
                ephemeral=True,
            )
            return

        if minutes < 1 or minutes > 9999:
            await interaction.response.send_message(
                config.MESSAGES["afk_invalid_minutes"],
                ephemeral=True,
            )
            return

        if afk.get_user_afk(interaction.guild.id, interaction.user.id):
            await interaction.response.send_message(
                config.MESSAGES["afk_already"],
                ephemeral=True,
            )
            return

        record = afk.set_afk(
            interaction.guild.id,
            interaction.user.id,
            reason,
            minutes,
        )
        until = int(record["until"])

        log_usage_from_interaction(
            interaction,
            "afk.start",
            details={
                "reason": reason[:200],
                "minutes": minutes,
                "until": until,
            },
            bot=interaction.client,  # type: ignore[arg-type]
        )

        await interaction.response.send_message(
            config.MESSAGES["afk_started"].format(
                reason=reason,
                until=f"<t:{until}:F>",
                relative=f"<t:{until}:R>",
            ),
            ephemeral=True,
        )


async def handle_afk_go(interaction: discord.Interaction) -> None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Доступно только на сервере.",
            ephemeral=True,
        )
        return

    if afk.get_user_afk(interaction.guild.id, interaction.user.id):
        await interaction.response.send_message(
            config.MESSAGES["afk_already"],
            ephemeral=True,
        )
        return

    await interaction.response.send_modal(AfkGoModal())
    log_usage_from_interaction(
        interaction,
        "panel.afk.go",
        bot=interaction.client,  # type: ignore[arg-type]
    )


async def handle_afk_leave(interaction: discord.Interaction) -> None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Доступно только на сервере.",
            ephemeral=True,
        )
        return

    if not afk.clear_afk(interaction.guild.id, interaction.user.id):
        await interaction.response.send_message(
            config.MESSAGES["afk_not_in"],
            ephemeral=True,
        )
        return

    log_usage_from_interaction(
        interaction,
        "afk.end",
        bot=interaction.client,  # type: ignore[arg-type]
    )
    await interaction.response.send_message(
        config.MESSAGES["afk_left"],
        ephemeral=True,
    )


async def handle_afk_list(interaction: discord.Interaction) -> None:
    if not interaction.guild:
        await interaction.response.send_message(
            "Доступно только на сервере.",
            ephemeral=True,
        )
        return

    text = afk.format_afk_list(interaction.guild, interaction.guild.id)
    if text == "—":
        await interaction.response.send_message(
            view=build_afk_list_empty_view(),
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        view=build_afk_list_view(text),
        ephemeral=True,
    )


def build_afk_buttons() -> list[ui.Button]:
    go_btn = ui.Button(
        label="Уйти в AFK",
        style=discord.ButtonStyle.secondary,
        custom_id=GO_ID,
        emoji="💤",
    )
    leave_btn = ui.Button(
        label="Выйти с AFK",
        style=discord.ButtonStyle.secondary,
        custom_id=LEAVE_ID,
        emoji="👋",
    )
    list_btn = ui.Button(
        label="Список AFK",
        style=discord.ButtonStyle.secondary,
        custom_id=LIST_ID,
        emoji="📋",
    )
    go_btn.callback = handle_afk_go
    leave_btn.callback = handle_afk_leave
    list_btn.callback = handle_afk_list
    return [go_btn, leave_btn, list_btn]


def attach_afk_buttons(view: ui.View) -> None:
    for btn in build_afk_buttons():
        view.add_item(btn)


def add_afk_buttons_to_row(row: ui.ActionRow) -> None:
    for btn in build_afk_buttons():
        row.add_item(btn)


class AfkActionView(ui.View):
    """Persistent view для кнопок AFK."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        attach_afk_buttons(self)
