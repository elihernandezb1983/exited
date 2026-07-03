"""Логирование модерации сервера и использования бота."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
from discord import ui

import config
from core import storage
from core.async_utils import fire_and_forget

if TYPE_CHECKING:
    from bot import GlowBot

DATA_DIR = config.BASE_DIR / "data" / "logs"
ACTIONS_FILE = DATA_DIR / "actions.jsonl"
USAGE_FILE = DATA_DIR / "usage.jsonl"

ACTION_ACCENT = config.EMBED_COLOR
USAGE_ACCENT = config.EMBED_COLOR

_lock = threading.Lock()

_KIND_META: dict[str, dict[str, str]] = {
    "panel.sent": {"emoji": "📤", "title": "Панель отправлена"},
    "ticket.created": {"emoji": "🎫", "title": "Создана заявка"},
    "ticket.accepted": {"emoji": "✅", "title": "Заявка принята"},
    "ticket.rejected": {"emoji": "❌", "title": "Заявка отклонена"},
    "ticket.settings.category": {"emoji": "📁", "title": "Тикеты: категория"},
    "ticket.settings.staff_add": {"emoji": "👁️", "title": "Тикеты: роль просмотра добавлена"},
    "ticket.settings.staff_remove": {"emoji": "🚫", "title": "Тикеты: роль просмотра убрана"},
    "ticket.settings.accepted_role": {"emoji": "🎖️", "title": "Тикеты: роль при принятии"},
    "ticket.cooldown.cleared": {"emoji": "⏱️", "title": "Тикеты: кулдаун снят"},
    "contract.created": {"emoji": "📋", "title": "Создан контракт"},
    "contract.joined": {"emoji": "🙋", "title": "Участие в контракте"},
    "contract.picked": {"emoji": "✅", "title": "Пик контракта"},
    "contract.declined": {"emoji": "❌", "title": "Отказ по контракту"},
    "gathering.created": {"emoji": "📢", "title": "Объявлен сбор"},
    "gathering.published": {"emoji": "📋", "title": "Опубликован список сбора"},
    "gathering.join_main": {"emoji": "✅", "title": "Запись в основу"},
    "gathering.join_reserve": {"emoji": "🔄", "title": "Запись в замену"},
    "panel.contracts.submit": {"emoji": "📋", "title": "Открыта форма контракта"},
    "modal.contracts.submit": {"emoji": "📨", "title": "Опубликован контракт"},
    "war.settings.stats_channel": {"emoji": "📊", "title": "Войны: канал статистики"},
    "war.settings.screenshots_channel": {"emoji": "📸", "title": "Войны: канал скринов"},
    "war.settings.cooldowns_channel": {"emoji": "⏱️", "title": "Войны: канал кулдаунов"},
    "war.settings.cd_attack": {"emoji": "🗡️", "title": "Войны: КД атаки"},
    "war.settings.cd_defense": {"emoji": "🛡️", "title": "Войны: КД защиты"},
    "war.settings.ping_role": {"emoji": "🔔", "title": "Войны: роль для тега"},
    "log.settings.actions_channel": {"emoji": "📋", "title": "Логи: канал модерации"},
    "log.settings.usage_channel": {"emoji": "🤖", "title": "Логи бота: канал команд"},
    "log.settings.enabled": {"emoji": "🟢", "title": "Логи включены"},
    "log.settings.disabled": {"emoji": "🔴", "title": "Логи выключены"},
    "mod.voice.move": {"emoji": "🔀", "title": "Перемещение в войсе"},
    "mod.voice.disconnect": {"emoji": "📴", "title": "Отключение из войса"},
    "mod.voice.server_mute": {"emoji": "🔇", "title": "Серверный мут"},
    "mod.voice.server_unmute": {"emoji": "🔊", "title": "Снят серверный мут"},
    "mod.voice.server_deaf": {"emoji": "🎧", "title": "Серверный deafen"},
    "mod.voice.server_undeaf": {"emoji": "👂", "title": "Снят серверный deafen"},
    "mod.timeout.set": {"emoji": "⏳", "title": "Тайм-аут"},
    "mod.timeout.remove": {"emoji": "✅", "title": "Тайм-аут снят"},
    "mod.kick": {"emoji": "👢", "title": "Кик"},
    "mod.ban": {"emoji": "🔨", "title": "Бан"},
    "mod.unban": {"emoji": "🔓", "title": "Разбан"},
    "mod.role.add": {"emoji": "➕", "title": "Выдана роль"},
    "mod.role.remove": {"emoji": "➖", "title": "Снята роль"},
    "panel.semya.apply": {"emoji": "📝", "title": "Открыта форма заявки"},
    "panel.vzp.map": {"emoji": "🗺️", "title": "Выбрана карта VZP"},
    "modal.semya.apply": {"emoji": "📨", "title": "Отправлена заявка в семью"},
    "ticket.review.accept": {"emoji": "✅", "title": "Нажато «Принять»"},
    "ticket.review.reject": {"emoji": "❌", "title": "Нажато «Отказать»"},
    "access.moderator.add": {"emoji": "🛡️", "title": "Добавлен модератор бота"},
    "access.moderator.remove": {"emoji": "🚫", "title": "Убран модератор бота"},
    "access.ticket.add": {"emoji": "🎫", "title": "Добавлен доступ к тикетам"},
    "access.ticket.remove": {"emoji": "➖", "title": "Убран доступ к тикетам"},
    "spam.sent": {"emoji": "📣", "title": "Спам-сообщения"},
    "afk.start": {"emoji": "💤", "title": "Ушёл в AFK"},
    "afk.end": {"emoji": "👋", "title": "Вышел из AFK"},
    "panel.afk.go": {"emoji": "💤", "title": "Открыта форма AFK"},
}

_DETAIL_LABELS: dict[str, str] = {
    "panel": "Панель",
    "panel_label": "Панель",
    "panel_id": "Панель",
    "channel_id": "Канал",
    "channel_name": "Канал",
    "from_channel_id": "Откуда",
    "from_channel_name": "Откуда",
    "to_channel_id": "Куда",
    "to_channel_name": "Куда",
    "category_id": "Категория",
    "category_name": "Категория",
    "role_id": "Роль",
    "role_name": "Роль",
    "ticket_number": "Номер заявки",
    "applicant_id": "Заявитель",
    "target_id": "Кому",
    "target_name": "Кому",
    "actor_id": "Модератор",
    "actor_name": "Модератор",
    "reason": "Причина",
    "map": "Карта",
    "minutes": "Минуты",
    "панель": "Панель",
    "канал": "Канал",
    "действие": "Действие",
    "категория": "Категория",
    "роль": "Роль",
    "минут": "Минуты",
}

_TICKET_SETUP_ACTIONS = {
    "category": "Категория для тикетов",
    "staff_add": "Роль просмотра — добавить",
    "staff_remove": "Роль просмотра — удалить",
    "accepted": "Роль при принятии",
    "list": "Показать настройки",
}

_WAR_SETUP_ACTIONS = {
    "stats": "Канал статистики",
    "screenshots": "Канал скринов",
    "cooldowns": "Канал кулдаунов",
    "cd_attack": "КД атаки",
    "cd_defense": "КД защиты",
    "ping_role": "Роль для тега",
    "list": "Показать настройки",
}

_LOG_SETUP_ACTIONS = {
    "actions": "Логи (модерация)",
    "usage": "Логи бота (команды)",
    "enable": "Включить логи",
    "disable": "Выключить логи",
    "list": "Показать настройки",
}


def _guild_settings(guild_id: int | None) -> dict[str, Any]:
    if guild_id is None:
        return {}
    return storage.get_guild(guild_id)


def _logging_enabled(guild_id: int | None) -> bool:
    if guild_id is None:
        return True
    return bool(_guild_settings(guild_id).get("audit_log_enabled", True))


def _actions_channel_id(guild_id: int | None) -> int | None:
    if guild_id is None:
        return None
    return _guild_settings(guild_id).get("log_actions_channel_id")


def _usage_channel_id(guild_id: int | None) -> int | None:
    if guild_id is None:
        return None
    return _guild_settings(guild_id).get("log_usage_channel_id")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)


def _kind_heading(kind: str) -> tuple[str, str]:
    if kind.startswith("command."):
        cmd = kind.removeprefix("command.")
        return "⚡", f"Команда /{cmd}"

    meta = _KIND_META.get(kind, {})
    emoji = meta.get("emoji", "📌")
    title = meta.get("title", kind.replace(".", " · ").replace("_", " "))
    return emoji, title


def _format_timestamp(iso_ts: str | None) -> str:
    if not iso_ts:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        unix = int(dt.timestamp())
        return f"<t:{unix}:F> · <t:{unix}:R>"
    except ValueError:
        return iso_ts


def _mention_user(user_id: int | None, user_name: str | None) -> str:
    if user_id:
        name = user_name or "Пользователь"
        return f"<@{user_id}> (`{name}`)"
    return user_name or "—"


def _mention_channel(channel_id: int | None, channel_name: str | None = None) -> str:
    if channel_id:
        label = f" #{channel_name}" if channel_name else ""
        return f"<#{channel_id}>{label}"
    return channel_name or "—"


def _mention_role(role_id: int | None, role_name: str | None = None) -> str:
    if role_id:
        return f"<@&{role_id}>" + (f" (`{role_name}`)" if role_name else "")
    return role_name or "—"


def _panel_label(panel_id: str | None) -> str | None:
    if not panel_id:
        return None
    cfg = config.PANELS.get(panel_id)
    return cfg["label"] if cfg else panel_id


def _format_detail_value(key: str, value: Any) -> str:
    if value is None:
        return "—"

    if key in ("channel_id", "канал", "from_channel_id", "to_channel_id"):
        try:
            return _mention_channel(int(value))
        except (TypeError, ValueError):
            return str(value)

    if key in ("category_id", "категория"):
        try:
            return _mention_channel(int(value))
        except (TypeError, ValueError):
            return str(value)

    if key in ("role_id", "роль", "applicant_id", "target_id", "actor_id"):
        try:
            num = int(value)
            if key in ("applicant_id", "target_id", "actor_id"):
                return f"<@{num}>"
            return _mention_role(num)
        except (TypeError, ValueError):
            return str(value)

    if key in ("panel", "panel_id", "панель"):
        return _panel_label(str(value)) or str(value)

    if key == "действие":
        action = str(value)
        for mapping in (_TICKET_SETUP_ACTIONS, _WAR_SETUP_ACTIONS, _LOG_SETUP_ACTIONS):
            if action in mapping:
                return mapping[action]
        return action

    if key == "minutes" and isinstance(value, (int, float, str)):
        try:
            mins = int(value)
            hours, rem = divmod(mins, 60)
            if hours and rem:
                return f"**{mins}** мин ({hours} ч {rem} мин)"
            if hours:
                return f"**{mins}** мин ({hours} ч)"
            return f"**{mins}** мин"
        except ValueError:
            pass

    if key == "ticket_number":
        return f"`ticket-{int(value):04d}`"

    if key in ("channel_name", "category_name", "role_name", "panel_label", "map", "target_name", "actor_name", "reason"):
        return f"**{value}**"

    return str(value)


def _format_details_block(details: dict[str, Any] | str | None) -> str | None:
    if details is None:
        return None
    if isinstance(details, str):
        return details

    skip_keys = {"panel_label", "channel_name", "category_name", "role_name"}
    lines: list[str] = []
    for key, value in details.items():
        if key in skip_keys:
            continue
        label = _DETAIL_LABELS.get(key, key.replace("_", " ").capitalize())
        lines.append(f"> **{label}:** {_format_detail_value(key, value)}")

    if not lines:
        for key, value in details.items():
            label = _DETAIL_LABELS.get(key, key.replace("_", " ").capitalize())
            lines.append(f"> **{label}:** {_format_detail_value(key, value)}")

    return "\n".join(lines) if lines else None


def build_log_view(record: dict[str, Any], *, log_type: str) -> ui.LayoutView:
    """Собрать Components V2 сообщение для канала логов."""
    kind = str(record.get("kind", "—"))
    emoji, title = _kind_heading(kind)
    accent = ACTION_ACCENT if log_type == "action" else USAGE_ACCENT

    user_id = record.get("user_id")
    user_name = record.get("user_name")
    channel_id = record.get("channel_id")
    ts = record.get("ts")
    details = record.get("details")

    header = f"## {emoji} {title}"
    who_line = f"**Кто:** {_mention_user(user_id, user_name)}"
    when_line = f"**Когда:** {_format_timestamp(ts)}"

    body_parts = [who_line, when_line]

    if log_type == "usage" and channel_id:
        body_parts.append(
            f"**Где:** {_mention_channel(channel_id)}",
        )

    details_block = _format_details_block(details)
    if details_block:
        body_parts.append("")
        body_parts.append("**Подробности**")
        body_parts.append(details_block)

    container = ui.Container(accent_color=discord.Colour(accent))
    container.add_item(ui.TextDisplay(header))
    container.add_item(
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    )
    container.add_item(ui.TextDisplay("\n".join(body_parts)))
    container.add_item(
        ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    )
    container.add_item(
        ui.TextDisplay(
            f"> {'Логи · модерация' if log_type == 'action' else 'Логи бота · команды'} · `{kind}`"
        ),
    )

    view = ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


async def _post_to_channel(
    bot: GlowBot,
    channel_id: int | None,
    *,
    log_type: str,
    record: dict[str, Any],
) -> None:
    if not channel_id:
        return
    await bot.wait_until_ready()
    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        try:
            channel = await bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
    if not isinstance(channel, discord.TextChannel):
        return

    view = build_log_view(record, log_type=log_type)
    try:
        await channel.send(view=view)
    except discord.HTTPException:
        pass


def log_action(
    kind: str,
    *,
    guild_id: int | None = None,
    user_id: int | None = None,
    user_name: str | None = None,
    details: dict[str, Any] | str | None = None,
    bot: GlowBot | None = None,
) -> None:
    """Записать событие модерации (мут, move, тайм-аут, роли и т.д.)."""
    if guild_id is not None and not _logging_enabled(guild_id):
        return

    record: dict[str, Any] = {
        "ts": _now_iso(),
        "kind": kind,
        "guild_id": guild_id,
        "user_id": user_id,
        "user_name": user_name,
        "details": details,
    }
    _append_jsonl(ACTIONS_FILE, record)

    if bot and guild_id is not None:
        fire_and_forget(
            _post_to_channel(
                bot,
                _actions_channel_id(guild_id),
                log_type="action",
                record=record,
            ),
            name="audit-action-discord",
        )


def log_usage(
    kind: str,
    *,
    guild_id: int | None = None,
    user_id: int | None = None,
    user_name: str | None = None,
    channel_id: int | None = None,
    details: dict[str, Any] | str | None = None,
    bot: GlowBot | None = None,
) -> None:
    """Записать использование бота (команды, кнопки, формы, настройки через бота)."""
    if guild_id is not None and not _logging_enabled(guild_id):
        return

    record: dict[str, Any] = {
        "ts": _now_iso(),
        "kind": kind,
        "guild_id": guild_id,
        "user_id": user_id,
        "user_name": user_name,
        "channel_id": channel_id,
        "details": details,
    }
    _append_jsonl(USAGE_FILE, record)

    if bot and guild_id is not None:
        fire_and_forget(
            _post_to_channel(
                bot,
                _usage_channel_id(guild_id),
                log_type="usage",
                record=record,
            ),
            name="audit-usage-discord",
        )


def _interaction_user(interaction: discord.Interaction) -> tuple[int | None, str | None]:
    user = interaction.user
    return user.id, str(user)


def log_moderation(
    kind: str,
    *,
    guild_id: int,
    actor_id: int | None = None,
    actor_name: str | None = None,
    target_id: int | None = None,
    target_name: str | None = None,
    details: dict[str, Any] | str | None = None,
    bot: GlowBot | None = None,
) -> None:
    """Записать модераторское действие на сервере."""
    merged: dict[str, Any] = {}
    if isinstance(details, dict):
        merged.update(details)
    if target_id is not None:
        merged.setdefault("target_id", target_id)
    if target_name is not None:
        merged.setdefault("target_name", target_name)
    if actor_id is not None:
        merged.setdefault("actor_id", actor_id)
    if actor_name is not None:
        merged.setdefault("actor_name", actor_name)

    log_action(
        kind,
        guild_id=guild_id,
        user_id=actor_id,
        user_name=actor_name,
        details=merged or None,
        bot=bot,
    )


def log_action_from_interaction(
    interaction: discord.Interaction,
    kind: str,
    *,
    details: dict[str, Any] | str | None = None,
    bot: GlowBot | None = None,
) -> None:
    user_id, user_name = _interaction_user(interaction)
    guild_id = interaction.guild.id if interaction.guild else None
    log_action(
        kind,
        guild_id=guild_id,
        user_id=user_id,
        user_name=user_name,
        details=details,
        bot=bot or _bot_from_interaction(interaction),
    )


def log_usage_from_interaction(
    interaction: discord.Interaction,
    kind: str,
    *,
    details: dict[str, Any] | str | None = None,
    bot: GlowBot | None = None,
) -> None:
    user_id, user_name = _interaction_user(interaction)
    guild_id = interaction.guild.id if interaction.guild else None
    channel_id = interaction.channel.id if interaction.channel else None
    log_usage(
        kind,
        guild_id=guild_id,
        user_id=user_id,
        user_name=user_name,
        channel_id=channel_id,
        details=details,
        bot=bot or _bot_from_interaction(interaction),
    )


def _bot_from_interaction(interaction: discord.Interaction) -> GlowBot | None:
    client = interaction.client
    if client is None:
        return None
    return client  # type: ignore[return-value]
