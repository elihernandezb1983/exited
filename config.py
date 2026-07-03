"""Конфигурация текстов, панелей и путей."""

from pathlib import Path

# Корень проекта
BASE_DIR = Path(__file__).resolve().parent
FOTO_DIR = BASE_DIR / "foto"
# Обратная совместимость в коде
FOTO_PANEL_DIR = FOTO_DIR
FOTO_VZP_DIR = FOTO_DIR

# Discord
BOT_TOKEN = ""  # или через .env: DISCORD_TOKEN

# ID сервера для быстрой синхронизации /панель (рекомендуется при разработке).
# В .env: GUILD_ID=123456789012345678
SYNC_GUILD_ID: int | None = None

# Глобальная синхронизация при каждом запуске — лимит Discord ~1 раз в час.
SYNC_GLOBAL_ON_START = False

# Цвет полоски embed и панелей Components V2
EMBED_COLOR = 0x000000

# Роли из config.py (устаревший fallback; лучше `/доступ-модератор`)
PANEL_ALLOWED_ROLE_IDS: list[int] = []

# Кулдаун между заявками в семью (дней)
TICKET_COOLDOWN_DAYS = 2

# --- Telegram (только войны → Discord) ---
TELEGRAM_API_ID: int | None = None
TELEGRAM_API_HASH: str = ""
TELEGRAM_PHONE: str = ""
TELEGRAM_CHATS: list[str] = []

# Канал Discord для embed статистики войн (или /война-канал)
WAR_CHANNEL_ID: int | None = None
# Канал для запроса скрина и приёма фото (или /война-канал-скрины)
WAR_REPORT_CHANNEL_ID: int | None = None
# Секунд ждать скрин после исхода (30 мин)
WAR_SCREENSHOT_TIMEOUT_SEC = 1800
# Роли для тега при запросе скрина (через запятую в .env)
WAR_PING_ROLE_IDS: list[int] = []
# Канал панели кулдаунов атаки/защиты (или /война-канал-кд)
WAR_CD_CHANNEL_ID: int | None = None
# Минуты кулдауна после забивки (атака 240 = 4 ч, защита 180 = 3 ч)
WAR_ATTACK_CD_MINUTES = 240
WAR_DEFENSE_CD_MINUTES = 180

# Карты VZP: название → файлы в foto/ (1–2 фото на карту)
VZP_MAPS: dict[str, list[str]] = {
    "Байкерка": ["1.png"],
    "Большой миррор": ["2.png"],
    "Веспуччи": ["3.png"],
    "Ветряки": ["4.png"],
    "Киностудия": ["5.png"],
    "Лесопилка": ["6.png"],
    "Маленький миррор": ["7.png"],
    "Муравейник": ["8.png"],
    "Мусорка": ["9.png"],
    "Мясо": ["10.png"],
    "Нефть": ["11.png", "11_2.png"],
    "Палетка": ["12.png"],
    "Порт Биз": ["13.png"],
    "Сендик": ["14.png"],
    "Стройка": ["15.png"],
    "Татушка": ["16.png"],
}

# --- Панели (ключ = значение в /панель) ---
PANELS: dict[str, dict] = {
    "semya": {
        "label": "Заявка в семью",
        "description": "Панель набора в семью с формой заявки",
        "image": "semya.png",
        "accent_color": 0x000000,
        "title": "### Оформление заявки в семью.",
        "body": (
            "Уведомление о приглашении на обзвон отправляется в личные сообщения.\n"
            "Заявки открыты только на **20 сервер Murrieta**\n\n"
            "> В среднем заявки обрабатываются в течение 5 часов\n\n"
            "Следите за статусом набора.\n"
            "**Если возможности заполнить заявку нет – набор закрыт.**\n"
            "**Каждое открытие набора сопровождается тегами в этом канале.**\n\n"
            "> В случае отказа можете подать заявку повторно через 2 дня"
        ),
        "select_section_label": "Подать заявку:",
        "select_placeholder": "Подать заявку в семью",
        "select_option_label": "Подать заявку",
        "select_option_description": "Открыть форму заявки",
        "select_custom_id": "panel:semya:apply",
    },
    "vzp": {
        "label": "VZP Maps",
        "description": "Панель карт VZP — выбор карты и 2 фото",
        "image": "vzp.png",
        "accent_color": 0x000000,
        "title": "### VZP MAPS",
        "body": " ",
        "select_section_label": "Выбери карту:",
        "select_placeholder": "Выбирай",
        "select_custom_id": "panel:vzp:map",
    },
    "contracts": {
        "label": "Контракты",
        "description": "Панель подачи контрактов и набора участников",
        "image": "contracts.png",
        "accent_color": 0x000000,
        "title": "### Контракты",
        "body": (
            "Подайте контракт — вы сразу попадёте в список участников (5 слотов).\n"
            "Остальные могут нажать **Участвовать**; модераторы — **Отказ** или **Пикнуть**."
        ),
        "select_section_label": "Действия:",
        "select_placeholder": "Подать контракт",
        "select_option_label": "Подать контракт",
        "select_option_description": "Открыть форму контракта",
        "select_custom_id": "panel:contracts:submit",
    },
    "afk": {
        "label": "AFK",
        "description": "Панель AFK — уйти, выйти, список",
        "image": "afk.png",
        "accent_color": 0x000000,
        "title": "### AFK",
        "body": (
            "Уйдите в AFK с указанием причины и времени.\n"
            "По истечении срока вы автоматически пропадёте из списка."
        ),
        "buttons_section_label": "Действия:",
    },
}

# --- Модальная форма заявки в семью ---
APPLICATION_MODAL = {
    "title": "Форма заявки",
    "custom_id": "modal:semya:apply",
    "fields": [
        {
            "id": "identity",
            "label": "Ваш ник | Сколько лет",
            "placeholder": "Owner_Exited 19",
            "style": "paragraph",
            "max_length": 1000,
            "required": True,
        },
        {
            "id": "online",
            "label": "Ваш средний онлайн + часовой пояс",
            "placeholder": "5ч, мск",
            "style": "short",
            "max_length": 100,
            "required": True,
        },
        {
            "id": "rollbacks",
            "label": "Откат арены DM 5-10 минут",
            "placeholder": "https://youtu.be/...",
            "style": "paragraph",
            "max_length": 1000,
            "required": True,
        },
        {
            "id": "experience",
            "label": "История семей",
            "placeholder": "Black,Consume,Gucci",
            "style": "paragraph",
            "max_length": 1000,
            "required": True,
        },
    ],
}

# --- Контракты ---
CONTRACT_SLOTS = 5

# --- Модальная форма контракта ---
CONTRACT_MODAL = {
    "title": "Подать контракт",
    "custom_id": "modal:contracts:submit",
    "fields": [
        {
            "id": "name",
            "label": "Какой контракт",
            "placeholder": "Например: Дальний коридор",
            "style": "short",
            "max_length": 100,
            "required": True,
        },
        {
            "id": "full_percent",
            "label": "На 100%",
            "placeholder": "Да / Нет",
            "style": "short",
            "max_length": 10,
            "required": True,
        },
    ],
}

# Сообщения
MESSAGES = {
    "panel_sent": "Панель **{panel}** отправлена в {channel}.",
    "panel_no_image": "Файл `{image}` не найден в `foto/`. Панель отправлена без картинки.",
    "application_sent": "Заявка отправлена. Канал: {channel}. Ожидайте ответа.",
    "ticket_embed_title": "Заявка в семью #{number}",
    "ticket_welcome": "ваша заявка. Ожидайте ответа в этом канале.",
    "ticket_review_prompt": "**Решение по заявке:**",
    "ticket_setup_need_category": "Для этого действия укажите параметр **категория**.",
    "ticket_setup_need_role": "Для этого действия укажите параметр **роль**.",
    "ticket_category_set": "Категория для тикетов: {category}",
    "ticket_role_added": "Роль {role} добавлена — видит каналы заявок.",
    "ticket_role_removed": "Роль {role} убрана из списка просмотра тикетов.",
    "ticket_role_exists": "Роль {role} уже в списке.",
    "ticket_role_missing": "Роли {role} нет в списке.",
    "ticket_settings_summary": (
        "**Настройки тикетов**\n"
        "Категория: {category}\n"
        "Роли тикетов (`/тикет-настройка`):\n{roles}\n"
        "Роль при принятии: {accepted_role}\n"
        "Следующий номер: `ticket-{next_number:04d}`"
    ),
    "ticket_accepted_role_set": "При принятии выдаётся роль {role}.",
    "ticket_accepted": "Заявка **принята**. {user} получил(а) {role}. Канал закрыт.",
    "ticket_accepted_left_server": (
        "Заявка **принята**. Пользователь вышел с сервера — "
        "роль {role} не выдана. Канал закрыт."
    ),
    "ticket_rejected": "Заявка **отклонена** ({user}). Канал закрыт.",
    "ticket_review_no_permission": "Принимать и отклонять могут только настроенные роли персонала.",
    "ticket_review_no_applicant": "Не удалось определить заявителя из сообщения.",
    "ticket_review_wrong_channel": "Кнопки работают только в канале тикета.",
    "ticket_no_accepted_role": (
        "Роль при принятии не задана. Настройте `/тикет-настройка` → «Роль при принятии»."
    ),
    "ticket_accepted_role_missing": "Настроенная роль при принятии удалена с сервера.",
    "ticket_role_grant_failed": (
        "Не удалось выдать роль: проверьте, что роль бота выше роли заявителя."
    ),
    "ticket_close_failed": "Не удалось удалить канал тикета (права бота).",
    "ticket_no_category": (
        "Тикеты не настроены: администратор должен указать категорию "
        "через `/тикет-настройка` → «Категория для тикетов»."
    ),
    "ticket_no_roles": (
        "Тикеты не настроены: добавьте роль персонала через "
        "`/тикет-настройка` → «Доступ к тикетам — добавить роль»."
    ),
    "ticket_cooldown_active": (
        "Вы уже подавали заявку недавно. Повторить можно через **{remaining}**."
    ),
    "ticket_cooldown_cleared": "Кулдаун на заявки снят для {user}.",
    "ticket_cooldown_not_set": "У {user} нет активного кулдауна на заявки.",
    "ticket_create_failed": "Не удалось создать канал заявки. Попробуйте позже.",
    "ticket_bot_permissions": (
        "У бота нет прав создавать каналы в категории. "
        "Выдайте **Управление каналами** и доступ к категории."
    ),
    "no_permission": "У вас нет прав на использование этой команды.",
    "access_manage_denied": (
        "Настраивать доступ могут только администраторы и пользователи "
        "с правом **Управление сервером**."
    ),
    "access_need_role": "Укажите параметр **роль**.",
    "access_moderator_added": (
        "Роль {role} добавлена в **модераторы бота** "
        "(панель, сборы, контракты, войны)."
    ),
    "access_moderator_removed": "Роль {role} убрана из модераторов бота.",
    "access_moderator_exists": "Роль {role} уже в списке модераторов.",
    "access_moderator_missing": "Роли {role} нет в списке модераторов.",
    "access_moderator_list": (
        "**Роли модераторов бота**\n{roles}\n\n"
        "Дают доступ: `/панель`, `/сбор`, модерация контрактов и сборов, `/война-настройка`."
    ),
    "access_ticket_added": (
        "Роль {role} добавлена в **персонал тикетов** "
        "(просмотр каналов и кнопки принять/отказать)."
    ),
    "access_ticket_removed": "Роль {role} убрана из персонала тикетов.",
    "access_ticket_exists": "Роль {role} уже в списке тикетов.",
    "access_ticket_missing": "Роли {role} нет в списке тикетов.",
    "access_ticket_list": (
        "**Роли персонала тикетов**\n{roles}\n\n"
        "Дают доступ: просмотр каналов заявок, кнопки **Принять** / **Отказать**."
    ),
    "vzp_map_no_images": (
        "Фото для **{map}** не найдены в `{folder}/`.\n"
        "Нужны файлы: {files}"
    ),
    "war_channel_set": "Статистика войн (embed) → {channel}.",
    "war_report_channel_set": "Запрос скрина и фото → {channel}.",
    "war_report_channel_missing": (
        "Канал для скринов не настроен. `/война-настройка` → «Канал скринов» "
        "или **WAR_REPORT_CHANNEL_ID** в .env."
    ),
    "war_setup_need_channel": "Укажите параметр **канал**.",
    "war_setup_need_role": "Укажите параметр **роль**.",
    "war_setup_need_minutes": "Укажите параметр **минут** (от 1 до 1440).",
    "war_cd_minutes_set": "КД **{kind}** — **{minutes} мин**. Панель обновлена.",
    "war_settings_summary": (
        "**Настройки войн**\n"
        "• Статистика (embed): {stats}\n"
        "• Скрины: {screenshots}\n"
        "• Кулдауны: {cooldowns}\n"
        "• КД атаки: **{attack_cd} мин** · защиты: **{defense_cd} мин**\n"
        "• Роль для тега: {ping_role}"
    ),
    "war_parse_failed": "Не удалось разобрать текст. Скопируйте сообщение из TG целиком.",
    "war_test_sent": "Отправлено в канал войн (как из Telegram).",
    "war_ping_screenshot": (
        "{mentions} — скиньте **скрин боя** "
        "(ответом на это сообщение или фото в этот канал, **30 мин**).\n"
        "**{location}** · бой **#{battle_id}** · **{outcome}**"
    ),
    "war_screenshot_done": "✅ Скрин добавлен в embed.",
    "war_ping_role_set": "Для тега при исходе будет использоваться {role}.",
    "war_cd_channel_set": (
        "Панель кулдаунов отправлена в {channel}. "
        "При забивке из TG таймеры обновятся автоматически."
    ),
    "log_setup_need_channel": "Укажите параметр **канал**.",
    "log_actions_channel_set": "Канал **логов** (мут, move и т.д.) → {channel}.",
    "log_usage_channel_set": "Канал **логов бота** (кто какие команды использует) → {channel}.",
    "log_enabled": "Логирование на этом сервере **включено**.",
    "log_disabled": "Логирование на этом сервере **выключено**.",
    "log_settings_summary": (
        "**Настройки логов**\n"
        "• Статус: {status}\n"
        "• Логи (модерация): {actions}\n"
        "• Логи бота (команды): {usage}"
    ),
    "contract_posted": "Контракт опубликован: {jump_url}",
    "contract_joined": "Вы добавлены в список участников.",
    "contract_already_joined": "Вы уже в списке участников.",
    "contract_full": "Набор участников уже завершён (5/5).",
    "contract_closed": "По этому контракту уже вынесено решение.",
    "contract_staff_only": "Только модераторы бота могут отказать или пикнуть контракт.",
    "contract_decline_reason_posted": "Отказ оформлен — сообщение отправлено в ветку.",
    "contract_picked": "Участники уведомлены о пике.",
    "contract_invalid_full_percent": "Ответьте **Да** или **Нет**.",
    "contract_not_found": "Контракт не найден или устарел.",
    "contract_wrong_channel": "Контракты можно подавать только в текстовом канале.",
    "contract_create_failed": "Не удалось опубликовать контракт. Попробуйте позже.",
    "contract_decline_thread": (
        "{participants} Вас отказали по контракту **{name}**.\n"
        "Модератор: {moderator}\n"
        "Причина: {reason}"
    ),
    "contract_pick_message": (
        "{participants} Вас пикнули по контракту **{name}**. "
        "Модератор: **{moderator}**"
    ),
    "gathering_posted": "Сбор опубликован в {channel}: {jump_url}",
    "gathering_ping": "{role} **Сбор на {mp}!**",
    "gathering_invalid_time": (
        "Неверное время. Примеры: `15` (через 15 мин), `15:00`, `15 00`."
    ),
    "gathering_need_mp": "Укажите, что за МП.",
    "gathering_wrong_channel": "Сбор можно отправить только в текстовый канал.",
    "gathering_send_failed": "Не удалось опубликовать сбор. Проверьте права бота.",
    "gathering_not_found": "Сбор не найден или устарел.",
    "gathering_closed": "Список уже опубликован — запись закрыта.",
    "gathering_main_full": "Основа заполнена. Запишитесь в **замену**.",
    "gathering_already_main": "Вы уже в основе.",
    "gathering_already_reserve": "Вы уже в замене.",
    "gathering_not_in_list": "Вас нет в списке сбора.",
    "gathering_joined_main": "Вы записаны в **основу**.",
    "gathering_joined_reserve": "Вы записаны в **замену**.",
    "gathering_left": "Вы вышли из сбора.",
    "gathering_mod_only": "Модерация доступна организатору и модераторам бота.",
    "gathering_mod_menu": "**Модерация сбора**\nВыберите участника и действие:",
    "gathering_mod_empty": "В списке пока никого нет.",
    "gathering_mod_pick_user": "Сначала выберите участника в списке.",
    "gathering_mod_selected": "Выбран: {user}",
    "gathering_mod_moved_main": "{user} перенесён в **основу**.",
    "gathering_mod_moved_reserve": "{user} перенесён в **замену**.",
    "gathering_mod_kicked": "{user} убран из списка.",
    "gathering_published": "Список опубликован, кнопки заблокированы.",
    "spam_wrong_channel": "Спам можно отправить только в текстовый канал.",
    "spam_need_message": "Укажите текст сообщения.",
    "spam_send_failed": "Не удалось отправить сообщения. Проверьте права бота в канале.",
    "spam_no_everyone": "У бота нет права **Упоминание @everyone, @here и всех ролей** в этом канале.",
    "spam_done": "Отправлено **{sent}** сообщ. в {channel} с тегом {role}.",
    "afk_need_reason": "Укажите причину.",
    "afk_invalid_minutes": "Укажите число минут от **1** до **9999**.",
    "afk_already": "Вы уже в AFK. Сначала выйдите или дождитесь окончания времени.",
    "afk_not_in": "Вас нет в списке AFK.",
    "afk_started": (
        "Вы в AFK: **{reason}**\n"
        "До: {until} ({relative})"
    ),
    "afk_left": "Вы вышли из AFK.",
    "afk_list_empty": "Сейчас никого нет в AFK.",
    "afk_list": "**Кто в AFK:**\n\n{list}",
}
