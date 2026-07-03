"""Точка входа Discord-бота (Components V2 / LayoutView)."""

from __future__ import annotations

import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

import config
from core.console_log import detail, info
from contracts.views import ContractActionView
from gatherings.views import GatheringActionView
from panels import get_persistent_views
from telegram import TelegramBridge
from tickets.views import TicketReviewView
from war.handler import WarHandler

load_dotenv()


class GlowBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.moderation = True
        intents.voice_states = True

        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
        )
        self.telegram_bridge = TelegramBridge(self)
        self.war_handler = WarHandler(self)

    async def close(self) -> None:
        await self.telegram_bridge.stop()
        await super().close()

    async def setup_hook(self) -> None:
        await self.load_extension("cogs")
        for view in get_persistent_views():
            self.add_view(view)
        self.add_view(TicketReviewView())
        self.add_view(ContractActionView())
        self.add_view(GatheringActionView())
        await self._sync_app_commands()

        if self.telegram_bridge.is_enabled():
            await self.telegram_bridge.start()

    async def _sync_app_commands(self) -> None:
        """Синхронизация slash-команд без глобального rate limit."""
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            guild_id = int(guild_id)
        elif config.SYNC_GUILD_ID:
            guild_id = config.SYNC_GUILD_ID

        if guild_id:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            # Убрать глобальные дубликаты (/панель дважды и т.д.)
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            detail(f"команды: {len(synced)} на сервере {guild_id}")
            return

        if config.SYNC_GLOBAL_ON_START or os.getenv("SYNC_GLOBAL", "").lower() in (
            "1",
            "true",
            "yes",
        ):
            synced = await self.tree.sync()
            detail(f"команды: {len(synced)} глобально")
            return

        detail("команды не синхронизированы (нужен GUILD_ID)")

    async def on_ready(self) -> None:
        info(f"Discord: {self.user}")
        await self.war_handler.cd_handler.resume_all()


async def main() -> None:
    token = os.getenv("DISCORD_TOKEN") or config.BOT_TOKEN
    if not token:
        raise SystemExit(
            "Укажите токен: переменная DISCORD_TOKEN в .env или BOT_TOKEN в config.py"
        )

    bot = GlowBot()
    try:
        async with bot:
            await bot.start(token)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен.")
