from __future__ import annotations

import discord
from discord import ui

import config
import contracts
import tickets
from audit_log import log_usage, log_usage_from_interaction
from contracts.views import build_contract_action_view


def _text_style(style: str) -> discord.TextStyle:
    return discord.TextStyle.paragraph if style == "paragraph" else discord.TextStyle.short


class ApplicationModal(ui.Modal):
    """Модальная форма заявки (настраивается через config.APPLICATION_MODAL)."""

    def __init__(self, modal_cfg: dict | None = None) -> None:
        cfg = modal_cfg or config.APPLICATION_MODAL
        super().__init__(title=cfg["title"], custom_id=cfg.get("custom_id"))

        self._field_ids: list[str] = []
        for field in cfg["fields"]:
            self._field_ids.append(field["id"])
            self.add_item(
                ui.TextInput(
                    label=field["label"],
                    placeholder=field.get("placeholder"),
                    style=_text_style(field.get("style", "short")),
                    max_length=field.get("max_length", 4000),
                    required=field.get("required", True),
                    custom_id=field["id"],
                )
            )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values = {child.custom_id: child.value for child in self.children if child.custom_id}

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Заявки принимаются только на сервере.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        remaining = tickets.get_ticket_cooldown_remaining(
            interaction.guild.id,
            interaction.user.id,
        )
        if remaining is not None:
            await interaction.followup.send(
                config.MESSAGES["ticket_cooldown_active"].format(
                    remaining=tickets.format_cooldown_remaining(remaining),
                ),
                ephemeral=True,
            )
            return

        try:
            tickets.validate_ticket_settings(interaction.guild.id)
        except ValueError as exc:
            if str(exc) == "no_category":
                msg = config.MESSAGES["ticket_no_category"]
            elif str(exc) == "no_staff_roles":
                msg = config.MESSAGES["ticket_no_roles"]
            else:
                msg = config.MESSAGES["ticket_create_failed"]
            await interaction.followup.send(msg, ephemeral=True)
            return

        channel: discord.TextChannel | None = None
        try:
            ticket_number = tickets.allocate_ticket_number(interaction.guild.id)
            channel = await tickets.create_ticket_channel(
                interaction.guild,
                interaction.user,
                ticket_number,
            )
            await tickets.send_ticket_opening(
                channel,
                interaction.user,
                ticket_number,
                values,
            )
            tickets.set_ticket_cooldown(interaction.guild.id, interaction.user.id)
        except ValueError:
            await interaction.followup.send(
                config.MESSAGES["ticket_create_failed"],
                ephemeral=True,
            )
            return
        except discord.Forbidden:
            await interaction.followup.send(
                config.MESSAGES["ticket_bot_permissions"],
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            try:
                await channel.delete(reason="Ошибка при создании заявки")
            except discord.HTTPException:
                pass
            await interaction.followup.send(
                config.MESSAGES["ticket_create_failed"] + f"\n`{exc}`",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            config.MESSAGES["application_sent"].format(channel=channel.mention),
            ephemeral=True,
        )

        log_usage_from_interaction(
            interaction,
            "modal.semya.apply",
            details={"ticket_number": ticket_number, "channel_id": channel.id},
            bot=interaction.client,  # type: ignore[arg-type]
        )
        log_usage(
            "ticket.created",
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            user_name=str(interaction.user),
            channel_id=channel.id,
            details={
                "ticket_number": ticket_number,
                "channel_id": channel.id,
                "channel_name": channel.name,
            },
            bot=interaction.client,  # type: ignore[arg-type]
        )


class ContractModal(ui.Modal):
    """Модальная форма контракта."""

    def __init__(self) -> None:
        cfg = config.CONTRACT_MODAL
        super().__init__(title=cfg["title"], custom_id=cfg.get("custom_id"))

        for field in cfg["fields"]:
            self.add_item(
                ui.TextInput(
                    label=field["label"],
                    placeholder=field.get("placeholder"),
                    style=_text_style(field.get("style", "short")),
                    max_length=field.get("max_length", 4000),
                    required=field.get("required", True),
                    custom_id=field["id"],
                )
            )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values = {child.custom_id: child.value for child in self.children if child.custom_id}

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Контракты доступны только на сервере.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                config.MESSAGES["contract_wrong_channel"],
                ephemeral=True,
            )
            return

        name = (values.get("name") or "").strip()
        full_percent_raw = (values.get("full_percent") or "").strip()
        people_count = config.CONTRACT_SLOTS

        if not name:
            await interaction.response.send_message(
                "Укажите название контракта.",
                ephemeral=True,
            )
            return

        full_percent_norm = full_percent_raw.lower()
        if full_percent_norm in ("да", "yes", "y"):
            full_percent = "да"
        elif full_percent_norm in ("нет", "no", "n"):
            full_percent = "нет"
        else:
            await interaction.response.send_message(
                config.MESSAGES["contract_invalid_full_percent"],
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        contract_data = {
            "creator_id": interaction.user.id,
            "channel_id": channel.id,
            "name": name,
            "people_count": people_count,
            "full_percent": full_percent,
            "participants": [interaction.user.id],
            "thread_id": None,
            "closed": False,
            "status": None,
            "status_label": None,
            "status_by": None,
            "status_at": None,
        }
        embed = contracts.build_contract_embed(interaction.guild, contract_data)
        view = build_contract_action_view()

        try:
            message = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send(
                config.MESSAGES["contract_create_failed"],
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                config.MESSAGES["contract_create_failed"],
                ephemeral=True,
            )
            return

        contracts.save_contract(interaction.guild.id, message.id, contract_data)

        await interaction.followup.send(
            config.MESSAGES["contract_posted"].format(jump_url=message.jump_url),
            ephemeral=True,
        )

        log_usage_from_interaction(
            interaction,
            "modal.contracts.submit",
            details={
                "contract_name": name,
                "people_count": people_count,
                "full_percent": full_percent,
                "message_id": message.id,
            },
            bot=interaction.client,  # type: ignore[arg-type]
        )
        log_usage(
            "contract.created",
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            user_name=str(interaction.user),
            channel_id=channel.id,
            details={
                "contract_name": name,
                "people_count": people_count,
                "full_percent": full_percent,
                "message_id": message.id,
            },
            bot=interaction.client,  # type: ignore[arg-type]
        )
