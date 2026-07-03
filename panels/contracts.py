from __future__ import annotations

import asyncio

import discord
from discord import ui

import config
from audit_log import log_usage_from_interaction
from core.async_utils import fire_and_forget

from .modals import ContractModal


class ContractsPanelView(ui.LayoutView):
    """Панель «Контракты» на Components V2."""

    def __init__(
        self,
        panel_cfg: dict,
        *,
        image_filename: str | None = None,
        image_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)
        self._panel_cfg = panel_cfg
        self._image_filename = image_filename
        self._image_url = image_url

        container = ui.Container(
            accent_color=discord.Colour(panel_cfg.get("accent_color", config.EMBED_COLOR)),
        )

        media_url = image_url
        if not media_url and image_filename:
            media_url = f"attachment://{image_filename}"

        if media_url:
            container.add_item(
                ui.MediaGallery(discord.MediaGalleryItem(media_url))
            )

        text = f"{panel_cfg['title']}\n\n{panel_cfg['body']}"
        container.add_item(ui.TextDisplay(text))
        container.add_item(
            ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
        )
        container.add_item(ui.TextDisplay(panel_cfg["select_section_label"]))

        row = ui.ActionRow()
        select = ui.Select(
            placeholder=panel_cfg["select_placeholder"],
            custom_id=panel_cfg["select_custom_id"],
            options=[
                discord.SelectOption(
                    label=panel_cfg["select_option_label"],
                    description=panel_cfg.get("select_option_description"),
                    value="submit",
                    emoji="📋",
                )
            ],
        )
        select.callback = self._on_select
        row.add_item(select)
        container.add_item(row)

        self.add_item(container)

    def _panel_image_url(self, message: discord.Message | None) -> str | None:
        if self._image_url:
            return self._image_url
        if message and message.attachments:
            return message.attachments[0].url
        return None

    async def _reset_select(self, interaction: discord.Interaction) -> None:
        message = interaction.message
        if not message:
            return
        await asyncio.sleep(0.4)
        try:
            view = fresh_contracts_view(
                self._panel_cfg,
                image_url=self._panel_image_url(message),
                image_filename=self._image_filename,
            )
            await message.edit(view=view)
        except discord.HTTPException:
            pass

    async def _on_select(self, interaction: discord.Interaction) -> None:
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

        await interaction.response.send_modal(ContractModal())
        log_usage_from_interaction(
            interaction,
            "panel.contracts.submit",
            bot=interaction.client,  # type: ignore[arg-type]
        )
        fire_and_forget(self._reset_select(interaction), name="panel-contracts-reset")


def fresh_contracts_view(
    panel_cfg: dict,
    *,
    image_url: str | None = None,
    image_filename: str | None = None,
) -> ContractsPanelView:
    return ContractsPanelView(
        panel_cfg,
        image_filename=image_filename,
        image_url=image_url,
    )
