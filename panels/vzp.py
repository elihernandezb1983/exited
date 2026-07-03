from __future__ import annotations

import asyncio
from pathlib import Path

import discord
from discord import ui

import config
from audit_log import log_usage_from_interaction
from core.async_utils import fire_and_forget


def find_map_images(map_name: str) -> list[Path]:
    """Файлы карты из словаря VZP_MAPS → foto/."""
    filenames = config.VZP_MAPS.get(map_name, [])
    paths: list[Path] = []
    for name in filenames:
        path = config.FOTO_DIR / name
        if path.is_file():
            paths.append(path)
    return paths


class VzpMapsPanelView(ui.LayoutView):
    """Панель выбора карт VZP."""

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
                discord.SelectOption(label=name, value=name)
                for name in config.VZP_MAPS
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
            view = fresh_vzp_view(
                self._panel_cfg,
                image_url=self._panel_image_url(message),
                image_filename=self._image_filename,
            )
            await message.edit(view=view)
        except discord.HTTPException:
            pass

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if not interaction.data.get("values"):
            return

        map_name = interaction.data["values"][0]
        if map_name not in config.VZP_MAPS:
            await interaction.response.send_message(
                "Неизвестная карта.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        log_usage_from_interaction(
            interaction,
            "panel.vzp.map",
            details={"map": map_name},
            bot=interaction.client,  # type: ignore[arg-type]
        )

        image_paths = find_map_images(map_name)
        expected = config.VZP_MAPS[map_name]
        if not image_paths:
            await interaction.followup.send(
                config.MESSAGES["vzp_map_no_images"].format(
                    map=map_name,
                    folder=config.FOTO_DIR.name,
                    files=", ".join(expected),
                ),
                ephemeral=True,
            )
            fire_and_forget(self._reset_select(interaction), name="panel-vzp-reset")
            return

        if len(image_paths) < len(expected):
            missing = [f for f in expected if not (config.FOTO_DIR / f).is_file()]
            await interaction.followup.send(
                config.MESSAGES["vzp_map_no_images"].format(
                    map=map_name,
                    folder=config.FOTO_DIR.name,
                    files=", ".join(missing),
                ),
                ephemeral=True,
            )
            fire_and_forget(self._reset_select(interaction), name="panel-vzp-reset")
            return

        files = [discord.File(p, filename=p.name) for p in image_paths]
        await interaction.followup.send(
            content=f"**{map_name}**",
            files=files,
            ephemeral=True,
        )
        fire_and_forget(self._reset_select(interaction), name="panel-vzp-reset")


def fresh_vzp_view(
    panel_cfg: dict,
    *,
    image_url: str | None = None,
    image_filename: str | None = None,
) -> VzpMapsPanelView:
    return VzpMapsPanelView(
        panel_cfg,
        image_filename=image_filename,
        image_url=image_url,
    )
