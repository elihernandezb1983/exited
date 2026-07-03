from __future__ import annotations

from pathlib import Path

import discord

import config
from .afk import AfkPanelView
from .family import FamilyPanelView
from .contracts import ContractsPanelView
from .vzp import VzpMapsPanelView


def _image_path(filename: str) -> Path:
    return config.FOTO_DIR / filename


def build_panel(panel_id: str) -> tuple[discord.ui.LayoutView, list[discord.File], str | None]:
    """
    Собрать LayoutView и файлы для панели.

    Returns:
        view, files, warning (если картинка не найдена)
    """
    if panel_id not in config.PANELS:
        raise KeyError(f"Неизвестная панель: {panel_id}")

    panel_cfg = config.PANELS[panel_id]
    files: list[discord.File] = []
    warning: str | None = None
    image_filename: str | None = None

    image_name = panel_cfg.get("image")
    if image_name:
        path = _image_path(image_name)
        if path.is_file():
            image_filename = image_name
            files.append(discord.File(path, filename=image_name))
        else:
            warning = config.MESSAGES["panel_no_image"].format(image=image_name)

    if panel_id == "semya":
        view = FamilyPanelView(panel_cfg, image_filename=image_filename)
    elif panel_id == "contracts":
        view = ContractsPanelView(panel_cfg, image_filename=image_filename)
    elif panel_id == "vzp":
        view = VzpMapsPanelView(panel_cfg, image_filename=image_filename)
    elif panel_id == "afk":
        view = AfkPanelView(panel_cfg, image_filename=image_filename)
    else:
        raise KeyError(f"Панель {panel_id!r} не реализована")

    return view, files, warning


def get_persistent_views() -> list[discord.ui.LayoutView]:
    """Views для регистрации после перезапуска бота (селекты с custom_id)."""
    views: list[discord.ui.LayoutView] = []
    for panel_id, panel_cfg in config.PANELS.items():
        if panel_id == "semya":
            views.append(
                FamilyPanelView(panel_cfg, image_filename=panel_cfg.get("image"))
            )
        elif panel_id == "contracts":
            views.append(
                ContractsPanelView(panel_cfg, image_filename=panel_cfg.get("image"))
            )
        elif panel_id == "vzp":
            views.append(
                VzpMapsPanelView(panel_cfg, image_filename=panel_cfg.get("image"))
            )
        elif panel_id == "afk":
            views.append(
                AfkPanelView(panel_cfg, image_filename=panel_cfg.get("image"))
            )
    return views
