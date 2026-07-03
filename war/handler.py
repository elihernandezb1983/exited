"""Telegram → Discord: embed, исход, скрин в embed."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from io import BytesIO
from typing import TYPE_CHECKING, Any

import discord

import config
from core.console_log import detail
from war.channels import resolve_channel_id
from war.embeds import build_war_embed, declare_title, player_outcome
from war.parser import WarEvent, WarEventKind, parse_war_message
from war.state import get_war_state, mutate_war, resolve_war_guild_ids

if TYPE_CHECKING:
    from bot import GlowBot

log = logging.getLogger(__name__)


def _normalize_location(name: str | None) -> str:
    return (name or "").strip().lower()


class WarHandler:
    def __init__(self, bot: GlowBot) -> None:
        self.bot = bot
        from war.cd_handler import CooldownHandler

        self.cd_handler = CooldownHandler(bot)

    def _screenshot_timeout(self) -> float:
        raw = os.getenv("WAR_SCREENSHOT_TIMEOUT_SEC", "")
        if raw:
            try:
                return float(raw)
            except ValueError:
                pass
        return float(config.WAR_SCREENSHOT_TIMEOUT_SEC)

    def _resolve_stats_channel_id(self, guild_id: int) -> int | None:
        return resolve_channel_id(
            guild_id,
            storage_key="war_channel_id",
            env_key="WAR_CHANNEL_ID",
            config_default=config.WAR_CHANNEL_ID,
        )

    def _resolve_report_channel_id(self, guild_id: int) -> int | None:
        return resolve_channel_id(
            guild_id,
            storage_key="war_report_channel_id",
            env_key="WAR_REPORT_CHANNEL_ID",
            config_default=config.WAR_REPORT_CHANNEL_ID,
        )

    async def _get_stats_channel(self, guild_id: int) -> discord.TextChannel | None:
        channel_id = self._resolve_stats_channel_id(guild_id)
        if not channel_id:
            return None
        await self.bot.wait_until_ready()
        return await self._get_text_channel(channel_id)

    async def _get_report_channel(self, guild_id: int) -> discord.TextChannel | None:
        channel_id = self._resolve_report_channel_id(guild_id)
        if not channel_id:
            return None
        await self.bot.wait_until_ready()
        return await self._get_text_channel(channel_id)

    def _ping_role_ids(self, guild_id: int) -> list[int]:
        war = get_war_state(guild_id)
        ids: list[int] = list(war.get("ping_role_ids") or [])
        if ids:
            return ids
        raw = os.getenv("WAR_PING_ROLE_IDS", "")
        if not raw and config.WAR_PING_ROLE_IDS:
            raw = ",".join(str(r) for r in config.WAR_PING_ROLE_IDS)
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return ids

    def _ping_mentions(self, guild: discord.Guild, guild_id: int) -> str:
        mentions: list[str] = []
        for role_id in self._ping_role_ids(guild_id):
            role = guild.get_role(role_id)
            if role:
                mentions.append(role.mention)
        return " ".join(mentions) if mentions else "@here"

    async def _get_text_channel(self, channel_id: int) -> discord.TextChannel | None:
        ch = self.bot.get_channel(channel_id)
        if isinstance(ch, discord.TextChannel):
            return ch
        try:
            fetched = await self.bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None
        return fetched if isinstance(fetched, discord.TextChannel) else None

    def _declare_to_dict(self, event: WarEvent) -> dict[str, Any]:
        return {
            "kind": event.kind.value,
            "opponent": event.opponent,
            "location": event.location,
            "location_norm": _normalize_location(event.location),
            "time": event.time,
            "format": event.format,
            "conditions": event.conditions,
        }

    def _outcome_to_dict(self, event: WarEvent) -> dict[str, Any]:
        return {
            "kind": event.kind.value,
            "location": event.location,
            "battle_id": event.battle_id,
        }

    def _dict_to_declare(self, data: dict[str, Any]) -> WarEvent:
        try:
            kind = WarEventKind(data["kind"])
        except ValueError:
            kind = WarEventKind.DEFENSE_DECLARE
        return WarEvent(
            kind=kind,
            opponent=data.get("opponent"),
            location=data.get("location"),
            time=data.get("time"),
            format=data.get("format"),
            conditions=data.get("conditions"),
        )

    def _dict_to_outcome(self, data: dict[str, Any]) -> WarEvent:
        try:
            kind = WarEventKind(data["kind"])
        except ValueError:
            kind = WarEventKind.LOSS
        return WarEvent(
            kind=kind,
            location=data.get("location"),
            battle_id=data.get("battle_id"),
        )

    async def _save_pending(
        self,
        *,
        guild_id: int,
        declare_data: dict[str, Any],
        message: discord.Message,
    ) -> None:
        declare_data = dict(declare_data)
        declare_data["embed_message_id"] = message.id
        declare_data["embed_channel_id"] = message.channel.id
        loc_key = declare_data.get("location_norm") or ""

        def _mutate(war: dict[str, Any]) -> None:
            war["last_declare"] = declare_data
            if loc_key:
                pending = dict(war.get("pending_by_location") or {})
                pending[loc_key] = declare_data
                war["pending_by_location"] = pending

        mutate_war(guild_id, _mutate)

    def _find_declare_for_outcome(
        self,
        war: dict[str, Any],
        outcome: WarEvent,
    ) -> dict[str, Any] | None:
        loc_key = _normalize_location(outcome.location)
        pending: dict[str, Any] = war.get("pending_by_location") or {}

        if loc_key and loc_key in pending:
            return pending[loc_key]

        if loc_key:
            for key, data in pending.items():
                if loc_key in key or key in loc_key:
                    return data

        last = war.get("last_declare")
        if isinstance(last, dict):
            last_loc = last.get("location_norm") or _normalize_location(
                last.get("location"),
            )
            if not loc_key or not last_loc or loc_key == last_loc:
                return last

        if len(pending) == 1:
            return next(iter(pending.values()))

        return None

    @staticmethod
    def _sync_embed_ids(data: dict[str, Any], message: discord.Message) -> dict[str, Any]:
        synced = dict(data)
        synced["embed_message_id"] = message.id
        synced["embed_channel_id"] = message.channel.id
        return synced

    async def _resolve_embed_channel(
        self,
        declare_data: dict[str, Any],
        fallback_channel: discord.TextChannel,
    ) -> discord.TextChannel:
        ch_id = declare_data.get("embed_channel_id")
        if ch_id:
            resolved = await self._get_text_channel(int(ch_id))
            if resolved:
                return resolved
        return fallback_channel

    async def _find_embed_message(
        self,
        channel: discord.TextChannel,
        *,
        msg_id: int | None,
        declare: WarEvent,
    ) -> discord.Message | None:
        if msg_id:
            try:
                return await channel.fetch_message(msg_id)
            except discord.NotFound:
                detail(
                    f"embed #{msg_id} не найден — ищем в #{channel.name}",
                )
            except discord.HTTPException:
                log.exception("Ошибка fetch_message(%s)", msg_id)

        if not self.bot.user:
            return None

        title = declare_title(declare.kind)
        opponent = (declare.opponent or "").strip().lower()

        async for msg in channel.history(limit=50):
            if msg.author.id != self.bot.user.id or not msg.embeds:
                continue
            emb = msg.embeds[0]
            if not emb.title or title not in emb.title:
                continue
            if opponent:
                body = " ".join(
                    f"{f.name} {f.value}" for f in emb.fields
                ).lower()
                if opponent not in body:
                    continue
            return msg

        return None

    async def _edit_outcome_embed(
        self,
        *,
        declare_data: dict[str, Any],
        declare: WarEvent,
        outcome: WarEvent,
        fallback_channel: discord.TextChannel,
        attachments: list[discord.File] | None = None,
    ) -> discord.Message | None:
        channel = await self._resolve_embed_channel(declare_data, fallback_channel)
        msg_id = declare_data.get("embed_message_id")
        msg = await self._find_embed_message(
            channel,
            msg_id=int(msg_id) if msg_id else None,
            declare=declare,
        )

        embed = build_war_embed(declare, outcome=outcome)
        files = attachments or []
        if files:
            embed.set_image(url=f"attachment://{files[0].filename}")

        if msg:
            try:
                await msg.edit(embed=embed, attachments=files)
                return msg
            except discord.HTTPException:
                log.exception("Не удалось изменить embed #%s", msg.id)

        try:
            new_msg = await channel.send(embed=embed, files=files)
            detail(f"новый embed → #{channel.name}")
            return new_msg
        except discord.HTTPException:
            log.exception("Не удалось отправить embed")
            return None

    def _clear_pending(
        self,
        guild_id: int,
        loc_key: str,
        declare_data: dict[str, Any],
    ) -> None:
        embed_id = declare_data.get("embed_message_id")

        def _mutate(war: dict[str, Any]) -> None:
            pending = dict(war.get("pending_by_location") or {})
            if loc_key and loc_key in pending:
                del pending[loc_key]
            war["pending_by_location"] = pending

            last = war.get("last_declare")
            if isinstance(last, dict) and last.get("embed_message_id") == embed_id:
                war["last_declare"] = None

        mutate_war(guild_id, _mutate)

    async def _delete_prompt_message(
        self,
        channel_id: int,
        prompt_id: int,
    ) -> None:
        channel = await self._get_text_channel(channel_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(prompt_id)
            await msg.delete()
        except discord.NotFound:
            pass
        except discord.HTTPException:
            log.exception("Не удалось удалить запрос скрина #%s", prompt_id)

    async def _prompt_cleanup_task(
        self,
        guild_id: int,
        channel_id: int,
        prompt_id: int,
        expires_at: float,
    ) -> None:
        try:
            delay = max(0.0, expires_at - time.time())
            await asyncio.sleep(delay)

            war = get_war_state(guild_id)
            pending = war.get("pending_report")
            if not isinstance(pending, dict):
                return
            if int(pending.get("prompt_message_id", 0)) != prompt_id:
                return

            await self._delete_prompt_message(channel_id, prompt_id)

            def _mutate(war: dict[str, Any]) -> None:
                war["pending_report"] = None

            mutate_war(guild_id, _mutate)
            detail("запрос скрина удалён (таймаут)")
        except Exception:
            log.exception("Ошибка таймера запроса скрина")

    def _schedule_prompt_cleanup(
        self,
        *,
        guild_id: int,
        channel_id: int,
        prompt_id: int,
        expires_at: float,
    ) -> None:
        self.bot.loop.create_task(
            self._prompt_cleanup_task(guild_id, channel_id, prompt_id, expires_at),
            name=f"war-prompt-{prompt_id}",
        )

    async def _request_screenshot(
        self,
        *,
        guild: discord.Guild,
        guild_id: int,
        declare: WarEvent,
        outcome: WarEvent,
        declare_data: dict[str, Any],
    ) -> None:
        report_channel = await self._get_report_channel(guild_id)
        if not report_channel:
            detail("канал скринов не настроен")
            log.warning("Война: канал скринов не настроен (WAR_REPORT_CHANNEL_ID)")
            return

        mentions = self._ping_mentions(guild, guild_id)
        location = declare.location or outcome.location or "—"
        battle_id = outcome.battle_id or 0
        outcome_text = player_outcome(declare, outcome)

        ping_text = config.MESSAGES["war_ping_screenshot"].format(
            mentions=mentions,
            location=location,
            battle_id=battle_id,
            outcome=outcome_text,
        )

        try:
            prompt = await report_channel.send(content=ping_text)
        except discord.HTTPException:
            log.exception("Не удалось отправить запрос скрина")
            return

        now = time.time()
        expires_at = now + self._screenshot_timeout()
        pending_report = {
            "declare": declare_data,
            "outcome": self._outcome_to_dict(outcome),
            "embed_message_id": declare_data.get("embed_message_id"),
            "embed_channel_id": declare_data.get("embed_channel_id"),
            "prompt_message_id": prompt.id,
            "report_channel_id": report_channel.id,
            "created_at": now,
            "expires_at": expires_at,
        }

        def _mutate(war: dict[str, Any]) -> None:
            war["pending_report"] = pending_report

        mutate_war(guild_id, _mutate)
        self._schedule_prompt_cleanup(
            guild_id=guild_id,
            channel_id=report_channel.id,
            prompt_id=prompt.id,
            expires_at=expires_at,
        )
        detail(f"скрин → #{report_channel.name}")

    async def on_discord_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        images = [
            a
            for a in message.attachments
            if a.content_type and a.content_type.startswith("image/")
        ]
        if not images:
            return

        war = get_war_state(message.guild.id)
        pending = war.get("pending_report")
        if not isinstance(pending, dict):
            return

        if int(pending.get("report_channel_id", 0)) != message.channel.id:
            return

        now = time.time()
        expires_at = float(pending.get("expires_at", 0))
        if now > expires_at:
            return

        prompt_id = pending.get("prompt_message_id")
        is_reply = (
            message.reference
            and message.reference.message_id == prompt_id
        )
        if message.reference and not is_reply:
            return

        declare = self._dict_to_declare(pending["declare"])
        outcome = self._dict_to_outcome(pending["outcome"])

        try:
            data = await images[0].read()
        except discord.HTTPException:
            log.exception("Не удалось скачать скрин")
            return

        filename = images[0].filename or "battle.png"
        file = discord.File(fp=BytesIO(data), filename=filename)

        declare_data = dict(pending["declare"])
        guild_id = message.guild.id
        stats_channel = await self._get_stats_channel(guild_id)
        if not stats_channel:
            return

        embed_msg = await self._edit_outcome_embed(
            declare_data=declare_data,
            declare=declare,
            outcome=outcome,
            fallback_channel=stats_channel,
            attachments=[file],
        )
        if not embed_msg:
            return

        declare_data = self._sync_embed_ids(declare_data, embed_msg)

        def _mutate(war: dict[str, Any]) -> None:
            war["pending_report"] = None

        mutate_war(guild_id, _mutate)

        if prompt_id:
            await self._delete_prompt_message(message.channel.id, int(prompt_id))

        try:
            await message.delete()
        except discord.HTTPException:
            log.warning("Не удалось удалить сообщение со скрином #%s", message.id)

        detail(f"скрин → #{message.channel.name}")

    async def _process_war_event(self, guild_id: int, event: WarEvent) -> None:
        channel = await self._get_stats_channel(guild_id)
        if not channel:
            log.warning(
                "Война: канал статистики не настроен на сервере %s "
                "(/война-настройка или WAR_CHANNEL_ID)",
                guild_id,
            )
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            try:
                guild = await self.bot.fetch_guild(guild_id)
            except discord.HTTPException:
                log.warning("Война: сервер %s недоступен", guild_id)
                return

        if event.kind in (WarEventKind.ATTACK_DECLARE, WarEventKind.DEFENSE_DECLARE):
            declare_data = self._declare_to_dict(event)
            embed = build_war_embed(event)
            msg = await channel.send(embed=embed)
            await self._save_pending(
                guild_id=guild_id,
                declare_data=declare_data,
                message=msg,
            )
            await self.cd_handler.on_declare(guild_id, event)
            return

        if event.kind not in (
            WarEventKind.ATTACK_WIN,
            WarEventKind.DEFENSE_WIN,
            WarEventKind.LOSS,
        ):
            return

        war = get_war_state(guild_id)
        declare_data = self._find_declare_for_outcome(war, event)

        if not declare_data:
            log.warning(
                "Война: исход без забивки на сервере %s (%s)",
                guild_id,
                event.location,
            )
            detail(f"исход без забивки [{guild_id}]: {event.location}")
            return

        declare = self._dict_to_declare(declare_data)
        loc_key = _normalize_location(event.location)

        declare_data = dict(declare_data)
        embed_msg = await self._edit_outcome_embed(
            declare_data=declare_data,
            declare=declare,
            outcome=event,
            fallback_channel=channel,
        )
        if embed_msg:
            declare_data = self._sync_embed_ids(declare_data, embed_msg)

        self._clear_pending(guild_id, loc_key, declare_data)

        await self._request_screenshot(
            guild=guild,
            guild_id=guild_id,
            declare=declare,
            outcome=event,
            declare_data=declare_data,
        )

    async def handle_telegram_text(self, text: str) -> bool:
        event = parse_war_message(text)
        if not event:
            return False

        guild_ids = resolve_war_guild_ids()
        if not guild_ids:
            log.warning("Война: укажите GUILD_ID или /война-канал")
            return True

        for guild_id in guild_ids:
            await self._process_war_event(guild_id, event)

        return True
