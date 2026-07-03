"""Кнопки «Принять» / «Отказать» на сообщении тикета."""

from __future__ import annotations

import re

import discord
from discord import ui

import config
from audit_log import log_usage_from_interaction
from core.permissions import can_review_ticket

ACCEPT_ID = "ticket:review:accept"
REJECT_ID = "ticket:review:reject"
APPLICANT_FOOTER_PREFIX = "applicant:"


def _can_review_ticket(interaction: discord.Interaction) -> bool:
    return can_review_ticket(interaction)


def applicant_id_from_message(message: discord.Message | None) -> int | None:
    if not message:
        return None
    if message.embeds:
        footer = message.embeds[0].footer.text or ""
        if footer.startswith(APPLICANT_FOOTER_PREFIX):
            try:
                return int(footer.removeprefix(APPLICANT_FOOTER_PREFIX))
            except ValueError:
                pass
        for field in message.embeds[0].fields:
            if field.name == "Заявитель":
                match = re.search(r"<@!?(\d+)>", field.value)
                if match:
                    return int(match.group(1))
    content = message.content or ""
    match = re.search(r"<@!?(\d+)>", content)
    if match:
        return int(match.group(1))
    return None


def _attach_review_buttons(view: ui.View) -> None:
    accept_btn = ui.Button(
        label="Принять",
        style=discord.ButtonStyle.success,
        custom_id=ACCEPT_ID,
        emoji="✅",
    )
    reject_btn = ui.Button(
        label="Отказать",
        style=discord.ButtonStyle.danger,
        custom_id=REJECT_ID,
        emoji="❌",
    )

    async def accept_callback(interaction: discord.Interaction) -> None:
        await _handle_review(interaction, accepted=True)

    async def reject_callback(interaction: discord.Interaction) -> None:
        await _handle_review(interaction, accepted=False)

    accept_btn.callback = accept_callback
    reject_btn.callback = reject_callback
    view.add_item(accept_btn)
    view.add_item(reject_btn)


def build_ticket_review_view() -> ui.View:
    """View с кнопками для нового тикета."""
    view = ui.View(timeout=None)
    _attach_review_buttons(view)
    return view


class TicketReviewView(ui.View):
    """Persistent view после перезапуска бота."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        _attach_review_buttons(self)


async def _find_applicant_id(
    interaction: discord.Interaction,
) -> int | None:
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        return None

    if interaction.message:
        found = applicant_id_from_message(interaction.message)
        if found is not None:
            return found

    async for message in channel.history(limit=20):
        if message.author.id != interaction.client.user.id:
            continue
        found = applicant_id_from_message(message)
        if found is not None:
            return found
    return None


async def _handle_review(interaction: discord.Interaction, *, accepted: bool) -> None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Доступно только на сервере.",
            ephemeral=True,
        )
        return

    if not _can_review_ticket(interaction):
        await interaction.response.send_message(
            config.MESSAGES["ticket_review_no_permission"],
            ephemeral=True,
        )
        return

    applicant_id = await _find_applicant_id(interaction)
    if applicant_id is None:
        await interaction.response.send_message(
            config.MESSAGES["ticket_review_no_applicant"],
            ephemeral=True,
        )
        return

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            config.MESSAGES["ticket_review_wrong_channel"],
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    log_usage_from_interaction(
        interaction,
        "ticket.review.accept" if accepted else "ticket.review.reject",
        details={"applicant_id": applicant_id},
        bot=interaction.client,  # type: ignore[arg-type]
    )

    applicant = channel.guild.get_member(applicant_id)
    if applicant is None:
        try:
            applicant = await channel.guild.fetch_member(applicant_id)
        except discord.NotFound:
            applicant = None

    status_msg = ""
    if accepted:
        settings = storage.get_guild(interaction.guild.id)
        role_id = settings.get("accepted_role_id")
        if not role_id:
            await interaction.followup.send(
                config.MESSAGES["ticket_no_accepted_role"],
                ephemeral=True,
            )
            return

        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.followup.send(
                config.MESSAGES["ticket_accepted_role_missing"],
                ephemeral=True,
            )
            return

        if applicant:
            try:
                await applicant.add_roles(
                    role,
                    reason=f"Заявка принята — {interaction.user}",
                )
                status_msg = config.MESSAGES["ticket_accepted"].format(
                    user=applicant.mention,
                    role=role.mention,
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    config.MESSAGES["ticket_role_grant_failed"],
                    ephemeral=True,
                )
                return
        else:
            status_msg = config.MESSAGES["ticket_accepted_left_server"].format(
                role=role.mention,
            )
    else:
        user_mention = applicant.mention if applicant else f"<@{applicant_id}>"
        status_msg = config.MESSAGES["ticket_rejected"].format(user=user_mention)

    if interaction.message and interaction.message.components:
        disabled = build_ticket_review_view()
        for child in disabled.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=disabled)
        except discord.HTTPException:
            pass

    reason = (
        f"Заявка принята — {interaction.user}"
        if accepted
        else f"Заявка отклонена — {interaction.user}"
    )
    try:
        await channel.delete(reason=reason)
    except discord.Forbidden:
        await interaction.followup.send(
            config.MESSAGES["ticket_close_failed"],
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        await interaction.followup.send(
            config.MESSAGES["ticket_close_failed"],
            ephemeral=True,
        )
        return

    log_usage_from_interaction(
        interaction,
        "ticket.accepted" if accepted else "ticket.rejected",
        details={
            "applicant_id": applicant_id,
            "channel_id": channel.id,
            "channel_name": channel.name,
        },
        bot=interaction.client,  # type: ignore[arg-type]
    )

    await interaction.followup.send(status_msg, ephemeral=True)
