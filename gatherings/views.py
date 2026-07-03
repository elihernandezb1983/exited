"""Кнопки сбора: основа, замена, выход, модерация."""

from __future__ import annotations

import discord
from discord import ui

import config
from audit_log import log_usage_from_interaction
from core.permissions import can_moderate

from . import service as gatherings

MAIN_ID = "gather:main"
RESERVE_ID = "gather:reserve"
LEAVE_ID = "gather:leave"
MOD_ID = "gather:mod"


def _can_moderate_gathering(interaction: discord.Interaction, data: dict) -> bool:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.id == int(data.get("creator_id", 0)):
        return True
    return can_moderate(interaction)


async def _fetch_gathering_message(
    interaction: discord.Interaction,
    data: dict,
    message_id: int,
) -> discord.Message | None:
    if not interaction.guild:
        return None
    if interaction.message and interaction.message.id == message_id:
        return interaction.message
    channel_id = data.get("channel_id")
    if not channel_id:
        return None
    channel = interaction.guild.get_channel(int(channel_id))
    if not isinstance(channel, discord.abc.Messageable):
        return None
    try:
        return await channel.fetch_message(message_id)
    except (discord.NotFound, discord.HTTPException):
        return None


async def _refresh_gathering_message(
    interaction: discord.Interaction,
    message_id: int,
    data: dict,
) -> None:
    if not interaction.guild:
        return
    message = await _fetch_gathering_message(interaction, data, message_id)
    if not message:
        return
    embed = gatherings.build_gathering_embed(interaction.guild, data)
    view = None if gatherings.is_gathering_published(data) else build_gathering_action_view()
    try:
        await message.edit(embed=embed, view=view)
    except discord.HTTPException:
        pass


def _add_to_main(record: dict, user_id: int) -> str | None:
    main = gatherings.main_ids(record)
    reserve = gatherings.reserve_ids(record)
    limit = gatherings.main_limit(record)

    if user_id in main:
        return "gathering_already_main"
    if len(main) >= limit:
        return "gathering_main_full"
    if user_id in reserve:
        reserve.remove(user_id)
    main.append(user_id)
    record["main"] = main
    record["reserve"] = reserve
    return None


def _add_to_reserve(record: dict, user_id: int) -> str | None:
    main = gatherings.main_ids(record)
    reserve = gatherings.reserve_ids(record)

    if user_id in reserve:
        return "gathering_already_reserve"
    if user_id in main:
        main.remove(user_id)
    reserve.append(user_id)
    record["main"] = main
    record["reserve"] = reserve
    return None


def _remove_user(record: dict, user_id: int) -> bool:
    main = gatherings.main_ids(record)
    reserve = gatherings.reserve_ids(record)
    removed = False
    if user_id in main:
        main.remove(user_id)
        removed = True
    if user_id in reserve:
        reserve.remove(user_id)
        removed = True
    record["main"] = main
    record["reserve"] = reserve
    return removed


class GatheringModerationView(ui.View):
    """Эфемерное меню модерации сбора."""

    def __init__(self, gathering_message_id: int) -> None:
        super().__init__(timeout=300)
        self._gathering_message_id = gathering_message_id
        self._selected_user_id: int | None = None
        self._select = ui.Select(
            placeholder="Выберите участника",
            min_values=1,
            max_values=1,
            options=[],
            row=0,
        )
        self._select.callback = self._on_select
        self.add_item(self._select)

        to_main = ui.Button(
            label="В основу",
            style=discord.ButtonStyle.primary,
            custom_id="gather:mod:main",
            row=1,
        )
        to_reserve = ui.Button(
            label="В замену",
            style=discord.ButtonStyle.secondary,
            custom_id="gather:mod:reserve",
            row=1,
        )
        kick = ui.Button(
            label="Выгнать",
            style=discord.ButtonStyle.danger,
            custom_id="gather:mod:kick",
            row=2,
        )
        publish = ui.Button(
            label="Опубликовать список",
            style=discord.ButtonStyle.success,
            custom_id="gather:mod:publish",
            row=2,
        )
        to_main.callback = self._on_to_main
        to_reserve.callback = self._on_to_reserve
        kick.callback = self._on_kick
        publish.callback = self._on_publish
        self.add_item(to_main)
        self.add_item(to_reserve)
        self.add_item(kick)
        self.add_item(publish)

    def _load_options(self, guild: discord.Guild, data: dict) -> bool:
        options: list[discord.SelectOption] = []
        for uid in gatherings.main_ids(data):
            member = guild.get_member(uid)
            label = member.display_name if member else str(uid)
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    value=str(uid),
                    description="Основа",
                ),
            )
        for uid in gatherings.reserve_ids(data):
            member = guild.get_member(uid)
            label = member.display_name if member else str(uid)
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    value=str(uid),
                    description="Замена",
                ),
            )
        if not options:
            return False
        self._select.options = options[:25]
        return True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        data = gatherings.get_gathering(interaction.guild.id, self._gathering_message_id)
        if not data:
            await interaction.response.send_message(
                config.MESSAGES["gathering_not_found"],
                ephemeral=True,
            )
            return False
        if gatherings.is_gathering_published(data):
            await interaction.response.send_message(
                config.MESSAGES["gathering_closed"],
                ephemeral=True,
            )
            return False
        if not _can_moderate_gathering(interaction, data):
            await interaction.response.send_message(
                config.MESSAGES["gathering_mod_only"],
                ephemeral=True,
            )
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values") if interaction.data else None
        if not values:
            await interaction.response.defer(ephemeral=True)
            return
        self._selected_user_id = int(values[0])
        await interaction.response.send_message(
            config.MESSAGES["gathering_mod_selected"].format(
                user=f"<@{self._selected_user_id}>",
            ),
            ephemeral=True,
        )

    async def _require_selection(self, interaction: discord.Interaction) -> int | None:
        if self._selected_user_id is None:
            await interaction.response.send_message(
                config.MESSAGES["gathering_mod_pick_user"],
                ephemeral=True,
            )
            return None
        return self._selected_user_id

    async def _on_to_main(self, interaction: discord.Interaction) -> None:
        user_id = await self._require_selection(interaction)
        if user_id is None:
            return

        def _mutate(record: dict) -> None:
            err = _add_to_main(record, user_id)
            if err:
                raise ValueError(err)

        try:
            updated = gatherings.mutate_gathering(
                interaction.guild.id,  # type: ignore[union-attr]
                self._gathering_message_id,
                _mutate,
            )
        except ValueError as exc:
            key = str(exc)
            await interaction.response.send_message(
                config.MESSAGES.get(key, config.MESSAGES["gathering_not_found"]),
                ephemeral=True,
            )
            return

        if not updated:
            await interaction.response.send_message(
                config.MESSAGES["gathering_not_found"],
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await _refresh_gathering_message(interaction, self._gathering_message_id, updated)
        await interaction.followup.send(
            config.MESSAGES["gathering_mod_moved_main"].format(user=f"<@{user_id}>"),
            ephemeral=True,
        )

    async def _on_to_reserve(self, interaction: discord.Interaction) -> None:
        user_id = await self._require_selection(interaction)
        if user_id is None:
            return

        def _mutate(record: dict) -> None:
            err = _add_to_reserve(record, user_id)
            if err:
                raise ValueError(err)

        try:
            updated = gatherings.mutate_gathering(
                interaction.guild.id,  # type: ignore[union-attr]
                self._gathering_message_id,
                _mutate,
            )
        except ValueError as exc:
            await interaction.response.send_message(
                config.MESSAGES.get(str(exc), config.MESSAGES["gathering_not_found"]),
                ephemeral=True,
            )
            return

        if not updated:
            await interaction.response.send_message(
                config.MESSAGES["gathering_not_found"],
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await _refresh_gathering_message(interaction, self._gathering_message_id, updated)
        await interaction.followup.send(
            config.MESSAGES["gathering_mod_moved_reserve"].format(user=f"<@{user_id}>"),
            ephemeral=True,
        )

    async def _on_kick(self, interaction: discord.Interaction) -> None:
        user_id = await self._require_selection(interaction)
        if user_id is None:
            return

        def _mutate(record: dict) -> None:
            if not _remove_user(record, user_id):
                raise ValueError("gathering_not_in_list")

        try:
            updated = gatherings.mutate_gathering(
                interaction.guild.id,  # type: ignore[union-attr]
                self._gathering_message_id,
                _mutate,
            )
        except ValueError:
            await interaction.response.send_message(
                config.MESSAGES["gathering_not_in_list"],
                ephemeral=True,
            )
            return

        if not updated:
            await interaction.response.send_message(
                config.MESSAGES["gathering_not_found"],
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await _refresh_gathering_message(interaction, self._gathering_message_id, updated)
        await interaction.followup.send(
            config.MESSAGES["gathering_mod_kicked"].format(user=f"<@{user_id}>"),
            ephemeral=True,
        )

    async def _on_publish(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        def _mutate(record: dict) -> None:
            record["published"] = True

        updated = gatherings.mutate_gathering(
            interaction.guild.id,
            self._gathering_message_id,
            _mutate,
        )
        if not updated:
            await interaction.response.send_message(
                config.MESSAGES["gathering_not_found"],
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        await _refresh_gathering_message(interaction, self._gathering_message_id, updated)

        log_usage_from_interaction(
            interaction,
            "gathering.published",
            details={
                "mp": updated["mp"],
                "message_id": self._gathering_message_id,
                "main_count": len(gatherings.main_ids(updated)),
                "reserve_count": len(gatherings.reserve_ids(updated)),
            },
            bot=interaction.client,  # type: ignore[arg-type]
        )

        await interaction.followup.send(
            config.MESSAGES["gathering_published"],
            ephemeral=True,
        )
        self.stop()


def _attach_gathering_buttons(view: ui.View) -> None:
    main_btn = ui.Button(
        label="В основу",
        style=discord.ButtonStyle.primary,
        custom_id=MAIN_ID,
        emoji="✅",
    )
    reserve_btn = ui.Button(
        label="В замену",
        style=discord.ButtonStyle.secondary,
        custom_id=RESERVE_ID,
        emoji="🔄",
    )
    leave_btn = ui.Button(
        label="Выйти",
        style=discord.ButtonStyle.danger,
        custom_id=LEAVE_ID,
        emoji="🚪",
    )
    mod_btn = ui.Button(
        label="Модерация",
        style=discord.ButtonStyle.success,
        custom_id=MOD_ID,
        emoji="🛠️",
    )

    main_btn.callback = _handle_main
    reserve_btn.callback = _handle_reserve
    leave_btn.callback = _handle_leave
    mod_btn.callback = _handle_mod
    view.add_item(main_btn)
    view.add_item(reserve_btn)
    view.add_item(leave_btn)
    view.add_item(mod_btn)


def build_gathering_action_view() -> ui.View:
    view = ui.View(timeout=None)
    _attach_gathering_buttons(view)
    return view


class GatheringActionView(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        _attach_gathering_buttons(self)


async def _handle_gathering_action(
    interaction: discord.Interaction,
    *,
    action: str,
) -> dict | None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Доступно только на сервере.",
            ephemeral=True,
        )
        return None

    message = interaction.message
    if not message:
        await interaction.response.send_message(
            config.MESSAGES["gathering_not_found"],
            ephemeral=True,
        )
        return None

    data = gatherings.get_gathering(interaction.guild.id, message.id)
    if not data:
        await interaction.response.send_message(
            config.MESSAGES["gathering_not_found"],
            ephemeral=True,
        )
        return None

    if gatherings.is_gathering_published(data):
        await interaction.response.send_message(
            config.MESSAGES["gathering_closed"],
            ephemeral=True,
        )
        return None

    user_id = interaction.user.id
    error_key: str | None = None

    def _mutate(record: dict) -> None:
        nonlocal error_key
        if action == "main":
            error_key = _add_to_main(record, user_id)
        elif action == "reserve":
            error_key = _add_to_reserve(record, user_id)
        elif action == "leave":
            if not _remove_user(record, user_id):
                error_key = "gathering_not_in_list"

    updated = gatherings.mutate_gathering(interaction.guild.id, message.id, _mutate)
    if not updated:
        await interaction.response.send_message(
            config.MESSAGES["gathering_not_found"],
            ephemeral=True,
        )
        return None

    if error_key:
        await interaction.response.send_message(
            config.MESSAGES[error_key],
            ephemeral=True,
        )
        return None

    await interaction.response.defer(ephemeral=True)
    await _refresh_gathering_message(interaction, message.id, updated)

    success_keys = {
        "main": "gathering_joined_main",
        "reserve": "gathering_joined_reserve",
        "leave": "gathering_left",
    }
    await interaction.followup.send(
        config.MESSAGES[success_keys[action]],
        ephemeral=True,
    )
    return updated


async def _handle_main(interaction: discord.Interaction) -> None:
    updated = await _handle_gathering_action(interaction, action="main")
    if updated:
        log_usage_from_interaction(
            interaction,
            "gathering.join_main",
            details={"mp": updated["mp"], "message_id": interaction.message.id},  # type: ignore[union-attr]
            bot=interaction.client,  # type: ignore[arg-type]
        )


async def _handle_reserve(interaction: discord.Interaction) -> None:
    updated = await _handle_gathering_action(interaction, action="reserve")
    if updated:
        log_usage_from_interaction(
            interaction,
            "gathering.join_reserve",
            details={"mp": updated["mp"], "message_id": interaction.message.id},  # type: ignore[union-attr]
            bot=interaction.client,  # type: ignore[arg-type]
        )


async def _handle_leave(interaction: discord.Interaction) -> None:
    await _handle_gathering_action(interaction, action="leave")


async def _handle_mod(interaction: discord.Interaction) -> None:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "Доступно только на сервере.",
            ephemeral=True,
        )
        return

    message = interaction.message
    if not message:
        await interaction.response.send_message(
            config.MESSAGES["gathering_not_found"],
            ephemeral=True,
        )
        return

    data = gatherings.get_gathering(interaction.guild.id, message.id)
    if not data:
        await interaction.response.send_message(
            config.MESSAGES["gathering_not_found"],
            ephemeral=True,
        )
        return

    if gatherings.is_gathering_published(data):
        await interaction.response.send_message(
            config.MESSAGES["gathering_closed"],
            ephemeral=True,
        )
        return

    if not _can_moderate_gathering(interaction, data):
        await interaction.response.send_message(
            config.MESSAGES["gathering_mod_only"],
            ephemeral=True,
        )
        return

    view = GatheringModerationView(message.id)
    if not view._load_options(interaction.guild, data):
        await interaction.response.send_message(
            config.MESSAGES["gathering_mod_empty"],
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        config.MESSAGES["gathering_mod_menu"],
        view=view,
        ephemeral=True,
    )
