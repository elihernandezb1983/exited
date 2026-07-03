from __future__ import annotations

import discord
from discord import ui

import config
from afk.views import add_afk_buttons_to_row


class AfkPanelView(ui.LayoutView):
    """Панель AFK на Components V2."""

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
        container.add_item(ui.TextDisplay(panel_cfg["buttons_section_label"]))

        row = ui.ActionRow()
        add_afk_buttons_to_row(row)
        container.add_item(row)

        self.add_item(container)


def fresh_afk_view(
    panel_cfg: dict,
    *,
    image_url: str | None = None,
    image_filename: str | None = None,
) -> AfkPanelView:
    return AfkPanelView(
        panel_cfg,
        image_filename=image_filename,
        image_url=image_url,
    )
