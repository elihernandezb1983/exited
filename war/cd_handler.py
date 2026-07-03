"""Обновление панели кулдаунов при забивках из Telegram."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import discord

import config
from core import storage
from core.console_log import detail
from war.channels import resolve_channel_id
from war.cooldowns import any_cd_active, build_cooldown_view, get_cd_state
from war.parser import WarEvent, WarEventKind
from war.state import (
    get_attack_cd_minutes,
    get_defense_cd_minutes,
    get_war_state,
    mutate_war,
)

if TYPE_CHECKING:
    from bot import GlowBot

log = logging.getLogger(__name__)


class CooldownHandler:
    def __init__(self, bot: GlowBot) -> None:
        self.bot = bot
        self._tick_tasks: dict[int, asyncio.Task] = {}

    def attack_cd_seconds(self, guild_id: int) -> float:
        war = get_war_state(guild_id)
        return get_attack_cd_minutes(war) * 60

    def defense_cd_seconds(self, guild_id: int) -> float:
        war = get_war_state(guild_id)
        return get_defense_cd_minutes(war) * 60

    def attack_cd_minutes(self, guild_id: int) -> int:
        return get_attack_cd_minutes(get_war_state(guild_id))

    def defense_cd_minutes(self, guild_id: int) -> int:
        return get_defense_cd_minutes(get_war_state(guild_id))

    def _resolve_cd_channel_id(self, guild_id: int) -> int | None:
        return resolve_channel_id(
            guild_id,
            storage_key="war_cd_channel_id",
            env_key="WAR_CD_CHANNEL_ID",
            config_default=config.WAR_CD_CHANNEL_ID,
        )

    async def _get_cd_channel(self, guild_id: int) -> discord.TextChannel | None:
        channel_id = self._resolve_cd_channel_id(guild_id)
        if not channel_id:
            return None
        await self.bot.wait_until_ready()
        return await self._get_text_channel(channel_id)

    async def _get_text_channel(self, channel_id: int) -> discord.TextChannel | None:
        ch = self.bot.get_channel(channel_id)
        if isinstance(ch, discord.TextChannel):
            return ch
        try:
            fetched = await self.bot.fetch_channel(channel_id)
        except discord.HTTPException:
            return None
        return fetched if isinstance(fetched, discord.TextChannel) else None

    async def on_declare(self, guild_id: int, event: WarEvent) -> None:
        if event.kind not in (
            WarEventKind.ATTACK_DECLARE,
            WarEventKind.DEFENSE_DECLARE,
        ):
            return

        channel = await self._get_cd_channel(guild_id)
        if not channel:
            detail("КД: канал не настроен (/война-настройка)")
            return

        now = time.time()

        def _mutate(war: dict[str, Any]) -> None:
            cd = get_cd_state(war)
            if event.kind == WarEventKind.ATTACK_DECLARE:
                cd["attack_until"] = now + self.attack_cd_seconds(guild_id)
            else:
                cd["defense_until"] = now + self.defense_cd_seconds(guild_id)
            war["cooldowns"] = cd

        mutate_war(guild_id, _mutate)

        await self._ensure_message(guild_id, channel)
        await self.refresh(guild_id)
        self._ensure_tick(guild_id)

    async def _ensure_message(
        self,
        guild_id: int,
        channel: discord.TextChannel,
    ) -> None:
        war = get_war_state(guild_id)
        cd = get_cd_state(war)
        msg_id = cd.get("message_id")
        ch_id = cd.get("channel_id")

        if msg_id and ch_id:
            old_ch = await self._get_text_channel(int(ch_id))
            if old_ch:
                try:
                    await old_ch.fetch_message(int(msg_id))
                    return
                except discord.NotFound:
                    pass
                except discord.HTTPException:
                    log.exception("КД: не удалось получить сообщение %s", msg_id)

        view = build_cooldown_view(
            cd,
            attack_minutes=self.attack_cd_minutes(guild_id),
            defense_minutes=self.defense_cd_minutes(guild_id),
        )
        try:
            msg = await channel.send(view=view)
        except discord.HTTPException:
            log.exception("КД: не удалось отправить панель")
            return

        sent_id = msg.id
        sent_ch = channel.id

        def _mutate(war: dict[str, Any]) -> None:
            stored = get_cd_state(war)
            stored["message_id"] = sent_id
            stored["channel_id"] = sent_ch
            war["cooldowns"] = stored

        mutate_war(guild_id, _mutate)

    async def refresh(self, guild_id: int) -> bool:
        war = get_war_state(guild_id)
        cd = get_cd_state(war)
        msg_id = cd.get("message_id")
        ch_id = cd.get("channel_id")
        if not msg_id or not ch_id:
            return False

        channel = await self._get_text_channel(int(ch_id))
        if not channel:
            return False

        try:
            msg = await channel.fetch_message(int(msg_id))
        except discord.NotFound:

            def _mutate(war: dict[str, Any]) -> None:
                stored = get_cd_state(war)
                stored["message_id"] = None
                war["cooldowns"] = stored

            mutate_war(guild_id, _mutate)
            return False
        except discord.HTTPException:
            log.exception("КД: fetch_message")
            return False

        view = build_cooldown_view(
            cd,
            attack_minutes=self.attack_cd_minutes(guild_id),
            defense_minutes=self.defense_cd_minutes(guild_id),
        )
        try:
            await msg.edit(view=view)
        except discord.HTTPException:
            log.exception("КД: edit")
            return False
        return True

    def _ensure_tick(self, guild_id: int) -> None:
        task = self._tick_tasks.get(guild_id)
        if task and not task.done():
            return
        self._tick_tasks[guild_id] = self.bot.loop.create_task(
            self._tick_loop(guild_id),
            name=f"war-cd-{guild_id}",
        )

    async def _tick_loop(self, guild_id: int) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                war = get_war_state(guild_id)
                cd = get_cd_state(war)
                if not cd.get("message_id"):
                    break
                if any_cd_active(cd):
                    await self.refresh(guild_id)
                    continue
                await self.refresh(guild_id)
                break
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("КД: tick guild=%s", guild_id)
        finally:
            self._tick_tasks.pop(guild_id, None)

    async def deploy_panel(self, guild_id: int, channel: discord.TextChannel) -> discord.Message:
        def _mutate(war: dict[str, Any]) -> None:
            cd = get_cd_state(war)
            cd["message_id"] = None
            cd["channel_id"] = channel.id
            war["cooldowns"] = cd

        mutate_war(guild_id, _mutate)
        storage.update_guild(guild_id, war_cd_channel_id=channel.id)
        await self._ensure_message(guild_id, channel)
        war = get_war_state(guild_id)
        cd = get_cd_state(war)
        panel_channel = await self._get_text_channel(int(cd["channel_id"]))
        msg = await panel_channel.fetch_message(int(cd["message_id"]))
        if any_cd_active(cd):
            self._ensure_tick(guild_id)
        return msg

    async def resume_all(self) -> None:
        await self.bot.wait_until_ready()
        for key in storage.get_all_guilds():
            guild_id = int(key)
            war = get_war_state(guild_id)
            cd = get_cd_state(war)
            if cd.get("message_id") and any_cd_active(cd):
                self._ensure_tick(guild_id)
