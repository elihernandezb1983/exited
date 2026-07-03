"""Кнопки «Участвовать» / «Отказ» / «Пикнуть» на embed контракта."""

from __future__ import annotations

import discord
from discord import ui

import config
from audit_log import log_usage_from_interaction
from core.permissions import can_moderate

from . import service as contracts

JOIN_ID = "contract:join"
DECLINE_ID = "contract:decline"
PICK_ID = "contract:pick"


def _can_moderate_contract(interaction: discord.Interaction) -> bool:
    return can_moderate(interaction)


async def _create_contract_thread(
    guild: discord.Guild,
    message: discord.Message,
    data: dict,
) -> discord.Thread | None:
    thread_id = data.get("thread_id")
    if thread_id:
        ch = guild.get_channel(thread_id)
        if isinstance(ch, discord.Thread):
            return ch

    try:
        thread = await message.create_thread(
            name=data["name"][:100],
            auto_archive_duration=1440,
            reason="Отказ по контракту",
        )
        contracts.mutate_contract(
            guild.id,
            message.id,
            lambda record: record.update({"thread_id": thread.id}),
        )
        return thread
    except discord.HTTPException:
        return None


class DeclineReasonModal(ui.Modal, title="Причина отказа"):
    reason = ui.TextInput(
        label="Причина отказа",
        placeholder="Кратко опишите причину",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True,
    )

    def __init__(self, message_id: int) -> None:
        super().__init__(custom_id=f"contract:decline:{message_id}")
        self._message_id = message_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Доступно только на сервере.",
                ephemeral=True,
            )
            return

        if not _can_moderate_contract(interaction):
            await interaction.response.send_message(
                config.MESSAGES["contract_staff_only"],
                ephemeral=True,
            )
            return

        message = interaction.message
        if not message:
            await interaction.response.send_message(
                config.MESSAGES["contract_not_found"],
                ephemeral=True,
            )
            return

        data = contracts.get_contract(interaction.guild.id, message.id)
        if not data:
            await interaction.response.send_message(
                config.MESSAGES["contract_not_found"],
                ephemeral=True,
            )
            return

        if contracts.is_contract_closed(data):
            await interaction.response.send_message(
                config.MESSAGES["contract_closed"],
                ephemeral=True,
            )
            return

        reason = self.reason.value.strip() or "—"
        from datetime import datetime, timezone

        status_at = datetime.now(timezone.utc).isoformat()

        def _close_declined(record: dict) -> None:
            record["closed"] = True
            record["status"] = "declined"
            record["status_label"] = f"Отказ: {reason}"
            record["status_by"] = interaction.user.id
            record["status_at"] = status_at

        updated = contracts.mutate_contract(
            interaction.guild.id,
            message.id,
            _close_declined,
        )
        if not updated:
            await interaction.response.send_message(
                config.MESSAGES["contract_not_found"],
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        participants: list[int] = list(updated.get("participants") or [])
        participants_text = contracts.participants_mentions(
            interaction.guild,
            participants,
        )
        thread = await _create_contract_thread(interaction.guild, message, updated)

        if thread:
            try:
                await thread.send(
                    config.MESSAGES["contract_decline_thread"].format(
                        participants=participants_text,
                        name=updated["name"],
                        moderator=interaction.user.mention,
                        reason=reason,
                    ),
                )
            except discord.HTTPException:
                pass

        embed = contracts.build_contract_embed(interaction.guild, updated)
        try:
            await message.edit(embed=embed, view=None)
        except discord.HTTPException:
            pass

        log_usage_from_interaction(
            interaction,
            "contract.declined",
            details={
                "contract_name": updated["name"],
                "reason": reason[:200],
            },
            bot=interaction.client,  # type: ignore[arg-type]
        )

        await interaction.followup.send(
            config.MESSAGES["contract_decline_reason_posted"],
            ephemeral=True,
        )


def _attach_contract_buttons(view: ui.View) -> None:
    join_btn = ui.Button(
        label="Участвовать",
        style=discord.ButtonStyle.primary,
        custom_id=JOIN_ID,
        emoji="🙋",
    )
    decline_btn = ui.Button(
        label="Отказ",
        style=discord.ButtonStyle.danger,
        custom_id=DECLINE_ID,
        emoji="❌",
    )
    pick_btn = ui.Button(
        label="Пикнуть",
        style=discord.ButtonStyle.success,
        custom_id=PICK_ID,
        emoji="✅",
    )

    async def join_callback(interaction: discord.Interaction) -> None:
        await _handle_join(interaction)

    async def decline_callback(interaction: discord.Interaction) -> None:
        await _handle_decline(interaction)

    async def pick_callback(interaction: discord.Interaction) -> None:
        await _handle_pick(interaction)

    join_btn.callback = join_callback
    decline_btn.callback = decline_callback
    pick_btn.callback = pick_callback
    view.add_item(join_btn)
    view.add_item(decline_btn)
    view.add_item(pick_btn)


def build_contract_action_view() -> ui.View:
    view = ui.View(timeout=None)
    _attach_contract_buttons(view)
    return view


class ContractActionView(ui.View):
    """Persistent view после перезапуска бота."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        _attach_contract_buttons(self)


async def _handle_join(interaction: discord.Interaction) -> None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Доступно только на сервере.",
            ephemeral=True,
        )
        return

    message = interaction.message
    if not message:
        await interaction.response.send_message(
            config.MESSAGES["contract_not_found"],
            ephemeral=True,
        )
        return

    data = contracts.get_contract(interaction.guild.id, message.id)
    if not data:
        await interaction.response.send_message(
            config.MESSAGES["contract_not_found"],
            ephemeral=True,
        )
        return

    if contracts.is_contract_closed(data):
        await interaction.response.send_message(
            config.MESSAGES["contract_closed"],
            ephemeral=True,
        )
        return

    user_id = interaction.user.id
    participants: list[int] = list(data.get("participants") or [])

    if user_id in participants:
        await interaction.response.send_message(
            config.MESSAGES["contract_already_joined"],
            ephemeral=True,
        )
        return

    people_count = contracts.slot_count(data)
    if len(participants) >= people_count:
        await interaction.response.send_message(
            config.MESSAGES["contract_full"],
            ephemeral=True,
        )
        return

    def _add_participant(record: dict) -> None:
        ids: list[int] = list(record.get("participants") or [])
        if user_id not in ids:
            ids.append(user_id)
        record["participants"] = ids

    updated = contracts.mutate_contract(
        interaction.guild.id,
        message.id,
        _add_participant,
    )
    if not updated:
        await interaction.response.send_message(
            config.MESSAGES["contract_not_found"],
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    embed = contracts.build_contract_embed(interaction.guild, updated)
    try:
        await message.edit(embed=embed)
    except discord.HTTPException:
        pass

    log_usage_from_interaction(
        interaction,
        "contract.joined",
        details={"contract_name": data["name"]},
        bot=interaction.client,  # type: ignore[arg-type]
    )

    await interaction.followup.send(
        config.MESSAGES["contract_joined"],
        ephemeral=True,
    )


async def _handle_pick(interaction: discord.Interaction) -> None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Доступно только на сервере.",
            ephemeral=True,
        )
        return

    if not _can_moderate_contract(interaction):
        await interaction.response.send_message(
            config.MESSAGES["contract_staff_only"],
            ephemeral=True,
        )
        return

    message = interaction.message
    if not message:
        await interaction.response.send_message(
            config.MESSAGES["contract_not_found"],
            ephemeral=True,
        )
        return

    data = contracts.get_contract(interaction.guild.id, message.id)
    if not data:
        await interaction.response.send_message(
            config.MESSAGES["contract_not_found"],
            ephemeral=True,
        )
        return

    if contracts.is_contract_closed(data):
        await interaction.response.send_message(
            config.MESSAGES["contract_closed"],
            ephemeral=True,
        )
        return

    from datetime import datetime, timezone

    status_at = datetime.now(timezone.utc).isoformat()

    def _close_picked(record: dict) -> None:
        record["closed"] = True
        record["status"] = "picked"
        record["status_label"] = "Пикнул"
        record["status_by"] = interaction.user.id
        record["status_at"] = status_at

    updated = contracts.mutate_contract(
        interaction.guild.id,
        message.id,
        _close_picked,
    )
    if not updated:
        await interaction.response.send_message(
            config.MESSAGES["contract_not_found"],
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    participants: list[int] = list(updated.get("participants") or [])
    participants_text = contracts.participants_mentions(
        interaction.guild,
        participants,
    )
    channel = message.channel
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(
                config.MESSAGES["contract_pick_message"].format(
                    participants=participants_text,
                    name=updated["name"],
                    moderator=interaction.user.mention,
                ),
            )
        except discord.HTTPException:
            pass

    embed = contracts.build_contract_embed(interaction.guild, updated)
    try:
        await message.edit(embed=embed, view=None)
    except discord.HTTPException:
        pass

    log_usage_from_interaction(
        interaction,
        "contract.picked",
        details={"contract_name": updated["name"]},
        bot=interaction.client,  # type: ignore[arg-type]
    )

    await interaction.followup.send(
        config.MESSAGES["contract_picked"],
        ephemeral=True,
    )


async def _handle_decline(interaction: discord.Interaction) -> None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Доступно только на сервере.",
            ephemeral=True,
        )
        return

    if not _can_moderate_contract(interaction):
        await interaction.response.send_message(
            config.MESSAGES["contract_staff_only"],
            ephemeral=True,
        )
        return

    message = interaction.message
    if not message:
        await interaction.response.send_message(
            config.MESSAGES["contract_not_found"],
            ephemeral=True,
        )
        return

    data = contracts.get_contract(interaction.guild.id, message.id)
    if not data:
        await interaction.response.send_message(
            config.MESSAGES["contract_not_found"],
            ephemeral=True,
        )
        return

    if contracts.is_contract_closed(data):
        await interaction.response.send_message(
            config.MESSAGES["contract_closed"],
            ephemeral=True,
        )
        return

    await interaction.response.send_modal(DeclineReasonModal(message.id))
