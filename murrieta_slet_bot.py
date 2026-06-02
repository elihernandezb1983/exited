"""
Монитор слётов и покупок квартир GTA5RP через wiki.gta5rp.com/realestate.
Уведомления: только слёт в гос (пустой владелец) и покупка из гос.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

MSK = ZoneInfo("Europe/Moscow")
WIKI_URL = "https://wiki.gta5rp.com/realestate"
ACTION_ID = "400893e59a7d6b84839aba936a875293789e12fa69"
DB_PATH = Path(__file__).resolve().parent / "apartments_state.db"
LOCK_PATH = DB_PATH.with_name(".murrieta_slet_bot.lock")
_DB_LOCK_MARKERS = ("database is locked", "database is busy")
_instance_lock_handle = None


def _is_sqlite_lock_error(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    return any(marker in msg for marker in _DB_LOCK_MARKERS)


def configure_connection(conn: sqlite3.Connection) -> None:
    # busy_timeout должен быть первым — иначе WAL/PRAGMA падают сразу с locked.
    db_execute(conn, "PRAGMA busy_timeout=60000", retries=12)
    row = db_execute(conn, "PRAGMA journal_mode=WAL", retries=12).fetchone()
    mode = (row[0] if row else "").lower()
    if mode and mode != "wal":
        log.warning("SQLite journal_mode=%s (ожидался wal)", row[0])
    db_execute(conn, "PRAGMA synchronous=NORMAL", retries=4)


def _db_locked_help() -> str:
    return (
        "База apartments_state.db занята другим процессом. "
        "Остановите второй экземпляр murrieta_slet_bot.py в терминале/диспетчере задач "
        "и закройте файл базы в DB Browser или другом редакторе."
    )


def acquire_instance_lock() -> None:
    """Не даёт запустить два бота одновременно (частая причина database is locked)."""
    global _instance_lock_handle
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_PATH, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError):
        fh.close()
        log.error(
            "Бот уже запущен (занят %s). Закрой другой терминал с этим скриптом.",
            LOCK_PATH.name,
        )
        sys.exit(1)
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()).encode())
    fh.flush()
    _instance_lock_handle = fh

    def _release() -> None:
        global _instance_lock_handle
        if _instance_lock_handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(_instance_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(_instance_lock_handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        _instance_lock_handle.close()
        _instance_lock_handle = None

    atexit.register(_release)


def open_db() -> sqlite3.Connection:
    delay = 0.15
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(10):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=60.0)
            configure_connection(conn)
            return conn
        except sqlite3.OperationalError as exc:
            if not _is_sqlite_lock_error(exc):
                raise
            last_exc = exc
            if attempt >= 9:
                break
            time.sleep(delay)
            delay = min(delay * 2, 3.0)
    raise RuntimeError(_db_locked_help()) from last_exc


def db_execute(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple | list = (),
    *,
    retries: int = 8,
) -> sqlite3.Cursor:
    delay = 0.05
    for attempt in range(retries):
        try:
            return conn.execute(sql, params)
        except sqlite3.OperationalError as exc:
            if not _is_sqlite_lock_error(exc) or attempt >= retries - 1:
                raise
            conn.rollback()
            time.sleep(delay)
            delay = min(delay * 2, 2.0)
    raise RuntimeError("unreachable")


# Все сервера GTA5RP (sid как на вики)
ALL_SERVERS: list[tuple[str, str]] = [
    ("01", "Downtown"),
    ("02", "Strawberry"),
    ("03", "Vinewood"),
    ("04", "Blackberry"),
    ("05", "Insquad"),
    ("06", "Sunrise"),
    ("07", "Rainbow"),
    ("08", "Richman"),
    ("09", "Eclipse"),
    ("10", "La Mesa"),
    ("11", "Burton"),
    ("12", "Rockford"),
    ("13", "Alta"),
    ("14", "Del Perro"),
    ("15", "Davis"),
    ("16", "Harmony"),
    ("17", "Redwood"),
    ("18", "Hawick"),
    ("19", "Grapeseed"),
    ("20", "Murrieta"),
    ("21", "Vespucci"),
    ("22", "Milton"),
    ("23", "La Puerta"),
    ("24", "Senora"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gta5rp_slet")


def load_env_file() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_chat_id(raw: str) -> str | int:
    value = raw.strip()
    if value.lstrip("-").isdigit():
        return int(value)
    return value


def resolve_chat_ids() -> list[str]:
    """TELEGRAM_CHAT_IDS или TELEGRAM_CHAT_ID — через запятую."""
    raw = os.environ.get("TELEGRAM_CHAT_IDS", "").strip()
    if not raw:
        raw = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def resolve_servers() -> list[tuple[str, str]]:
    raw = os.environ.get("GTA5RP_SERVER_SIDS", "").strip()
    if not raw:
        legacy = os.environ.get("GTA5RP_SERVER_SID", "").strip()
        if legacy:
            raw = legacy
    if not raw or raw.lower() in ("all", "*"):
        return list(ALL_SERVERS)
    wanted = {
        s.strip().zfill(2)
        for part in raw.replace(";", ",").split(",")
        for s in part.split()
        if s.strip()
    }
    picked = [(sid, name) for sid, name in ALL_SERVERS if sid in wanted]
    if not picked:
        raise RuntimeError(f"GTA5RP_SERVER_SIDS не распознан: {raw!r}")
    return picked


def storage_key(server_sid: str, kind: str, local_key: str) -> str:
    return f"{server_sid}:{kind}:{local_key}"


def is_vacant(owner_name: str | None) -> bool:
    return not owner_name or not str(owner_name).strip()


def fetch_catalog(server_sid: str) -> dict:
    resp = requests.post(
        WIKI_URL,
        headers={
            "Next-Action": ACTION_ID,
            "Accept": "text/x-component",
            "Content-Type": "application/json",
        },
        json=[server_sid],
        timeout=90,
    )
    resp.raise_for_status()
    for line in resp.text.splitlines():
        if line.startswith("1:"):
            return json.loads(line[2:])
    raise RuntimeError("В ответе вики нет строки с данными (1:...)")


def iter_apartments(data: dict):
    buildings = {b["id"]: b["name"] for b in data.get("apartmentHouses", [])}
    by_house = data.get("apartmentsByHouseId") or {}
    for house_id, apartments in by_house.items():
        building = buildings.get(int(house_id), f"Здание #{house_id}")
        for apt in apartments:
            yield {
                "kind": "apt",
                "key": f"{house_id}:{apt['id']}",
                "building": building,
                "name": apt.get("name") or f"#{apt['id']}",
                "class_name": apt.get("className") or "—",
                "price": apt.get("price"),
                "owner": (apt.get("ownerName") or "").strip(),
            }


def iter_houses(data: dict):
    for house in data.get("houses", []):
        hid = house["id"]
        title = house.get("name") or f"Дом #{hid}"
        yield {
            "kind": "house",
            "key": str(hid),
            "building": title,
            "name": title,
            "class_name": house.get("className") or "—",
            "price": house.get("price"),
            "owner": (house.get("ownerName") or "").strip(),
        }


def iter_properties(data: dict):
    yield from iter_apartments(data)
    yield from iter_houses(data)


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS apartments (
            storage_key TEXT PRIMARY KEY,
            server_sid TEXT NOT NULL,
            server_name TEXT NOT NULL,
            apt_key TEXT NOT NULL,
            owner TEXT NOT NULL,
            building TEXT NOT NULL,
            apt_name TEXT NOT NULL,
            class_name TEXT NOT NULL DEFAULT '',
            price INTEGER,
            property_type TEXT NOT NULL DEFAULT 'apt',
            is_vacant INTEGER NOT NULL DEFAULT 0,
            awaiting_purchase INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            storage_key TEXT NOT NULL,
            server_sid TEXT NOT NULL,
            server_name TEXT NOT NULL,
            property_type TEXT NOT NULL DEFAULT 'apt',
            event_type TEXT NOT NULL,
            old_owner TEXT NOT NULL,
            new_owner TEXT NOT NULL,
            building TEXT NOT NULL,
            apt_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    _migrate_db(conn)
    conn.commit()


def _normalize_legacy_storage(raw: str) -> tuple[str, str, str]:
    """Вернуть (server_sid, kind, local_key) из старого формата ключа."""
    parts = str(raw).split(":")
    if len(parts) >= 3 and parts[0].isdigit() and len(parts[0]) == 2:
        if parts[1] in ("apt", "house"):
            return parts[0], parts[1], ":".join(parts[2:])
        return parts[0], "apt", ":".join(parts[1:])
    if len(parts) >= 2 and parts[0].isdigit() and len(parts[0]) == 2:
        return parts[0], "apt", ":".join(parts[1:])
    return "20", "apt", str(raw)


def _migrate_storage_keys_with_kind(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT storage_key, server_sid FROM apartments"
    ).fetchall()
    for storage, sid in rows:
        parts = storage.split(":")
        if len(parts) >= 3 and parts[1] in ("apt", "house"):
            continue
        nsid, kind, local = _normalize_legacy_storage(storage)
        new_key = storage_key(nsid or sid, kind, local)
        if new_key == storage:
            continue
        conn.execute(
            "UPDATE apartments SET storage_key = ?, property_type = ? WHERE storage_key = ?",
            (new_key, kind, storage),
        )


def _migrate_apartments_legacy_table(conn: sqlite3.Connection) -> None:
    """Старая схема (apt_key PK) → storage_key + server_sid."""
    log.info("Миграция базы: мульти-сервер (старые ключи → Murrieta/20)")
    conn.execute(
        """
        CREATE TABLE apartments_new (
            storage_key TEXT PRIMARY KEY,
            server_sid TEXT NOT NULL,
            server_name TEXT NOT NULL,
            apt_key TEXT NOT NULL,
            owner TEXT NOT NULL,
            building TEXT NOT NULL,
            apt_name TEXT NOT NULL,
            class_name TEXT NOT NULL DEFAULT '',
            price INTEGER,
            property_type TEXT NOT NULL DEFAULT 'apt',
            is_vacant INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    col_list = [row[1] for row in conn.execute("PRAGMA table_info(apartments)")]
    for row in conn.execute("SELECT * FROM apartments").fetchall():
        old = dict(zip(col_list, row))
        raw = old.get("storage_key") or old.get("apt_key") or row[0]
        sid, kind, local = _normalize_legacy_storage(str(raw))
        name = next((n for s, n in ALL_SERVERS if s == sid), f"Server {sid}")
        storage = storage_key(sid, kind, local)
        conn.execute(
            """
            INSERT INTO apartments_new (
                storage_key, server_sid, server_name, apt_key, owner, building,
                apt_name, class_name, price, property_type, is_vacant, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                storage,
                sid,
                name,
                local,
                old.get("owner", ""),
                old.get("building", ""),
                old.get("apt_name", old.get("name", "")),
                old.get("class_name", ""),
                old.get("price"),
                kind,
                old.get("is_vacant", 0),
                old.get("updated_at", ""),
            ),
        )
    conn.execute("DROP TABLE apartments")
    conn.execute("ALTER TABLE apartments_new RENAME TO apartments")


def _migrate_db(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "apartments" not in tables:
        return

    if "events" in tables:
        ev_cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        if "property_type" not in ev_cols:
            conn.execute(
                "ALTER TABLE events ADD COLUMN property_type TEXT NOT NULL DEFAULT 'apt'"
            )

    cols = {row[1] for row in conn.execute("PRAGMA table_info(apartments)")}

    if "storage_key" not in cols:
        _migrate_apartments_legacy_table(conn)
        _migrate_init_flags(conn)
        return

    if "property_type" not in cols:
        log.info("Миграция: тип недвижимости (квартиры + дома)")
        conn.execute(
            "ALTER TABLE apartments ADD COLUMN property_type TEXT NOT NULL DEFAULT 'apt'"
        )

    cols = {row[1] for row in conn.execute("PRAGMA table_info(apartments)")}
    if "awaiting_purchase" not in cols:
        log.info("Миграция: флаг ожидания покупки после слёта")
        conn.execute(
            "ALTER TABLE apartments ADD COLUMN awaiting_purchase INTEGER NOT NULL DEFAULT 0"
        )

    _migrate_storage_keys_with_kind(conn)
    _migrate_init_flags(conn)


def _migrate_init_flags(conn: sqlite3.Connection) -> None:
    """Старый init_20 → init_20_apt, чтобы не слать ложные слёты по квартирам."""
    for sid, _ in ALL_SERVERS:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (f"init_{sid}",)
        ).fetchone()
        if row and row[0] == "1":
            set_part_initialized(conn, sid, "apt")


def get_known_owner(conn: sqlite3.Connection, key: str) -> str | None:
    row = db_execute(
        conn,
        "SELECT owner FROM apartments WHERE storage_key = ?",
        (key,),
    ).fetchone()
    return row[0] if row else None


def is_awaiting_purchase(conn: sqlite3.Connection, key: str) -> bool:
    """True только если бот зафиксировал слёт этой квартиры и ждёт покупку."""
    row = db_execute(
        conn,
        "SELECT awaiting_purchase FROM apartments WHERE storage_key = ?",
        (key,),
    ).fetchone()
    return bool(row and row[0])


def set_awaiting_purchase(conn: sqlite3.Connection, key: str, awaiting: bool) -> None:
    db_execute(
        conn,
        "UPDATE apartments SET awaiting_purchase = ? WHERE storage_key = ?",
        (1 if awaiting else 0, key),
    )


def count_db_properties(conn: sqlite3.Connection) -> dict[str, int]:
    total = conn.execute("SELECT COUNT(*) FROM apartments").fetchone()[0]
    apts = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE property_type = 'apt'"
    ).fetchone()[0]
    houses = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE property_type = 'house'"
    ).fetchone()[0]
    return {"total": int(total), "apt": int(apts), "house": int(houses)}


def is_part_initialized(conn: sqlite3.Connection, server_sid: str, kind: str) -> bool:
    row = db_execute(
        conn,
        "SELECT value FROM meta WHERE key = ?",
        (f"init_{server_sid}_{kind}",),
    ).fetchone()
    return row is not None and row[0] == "1"


def set_part_initialized(conn: sqlite3.Connection, server_sid: str, kind: str) -> None:
    db_execute(
        conn,
        """
        INSERT INTO meta (key, value) VALUES (?, '1')
        ON CONFLICT(key) DO UPDATE SET value = '1'
        """,
        (f"init_{server_sid}_{kind}",),
    )


def startup_sent(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'startup_sent'"
    ).fetchone()
    return row is not None and row[0] == "1"


def set_startup_sent(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES ('startup_sent', '1')
        ON CONFLICT(key) DO UPDATE SET value = '1'
        """
    )


def normalize_owner(owner: str | None) -> str:
    return "" if is_vacant(owner) else str(owner).strip()


def upsert_property(
    conn: sqlite3.Connection,
    storage: str,
    server_sid: str,
    server_name: str,
    item: dict,
    owner: str,
) -> None:
    now = datetime.now(MSK).isoformat(timespec="seconds")
    vacant = 1 if not owner else 0
    kind = item["kind"]
    db_execute(
        conn,
        """
        INSERT INTO apartments (
            storage_key, server_sid, server_name, apt_key, owner, building,
            apt_name, class_name, price, property_type, is_vacant, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(storage_key) DO UPDATE SET
            owner = excluded.owner,
            building = excluded.building,
            apt_name = excluded.apt_name,
            class_name = excluded.class_name,
            price = excluded.price,
            property_type = excluded.property_type,
            is_vacant = excluded.is_vacant,
            updated_at = excluded.updated_at
        """,
        (
            storage,
            server_sid,
            server_name,
            item["key"],
            owner,
            item["building"],
            item["name"],
            item["class_name"],
            item.get("price"),
            kind,
            vacant,
            now,
        ),
    )


def log_event(
    conn: sqlite3.Connection,
    storage: str,
    server_sid: str,
    server_name: str,
    property_type: str,
    event_type: str,
    old_owner: str,
    new_owner: str,
    building: str,
    apt_name: str,
) -> None:
    now = datetime.now(MSK).isoformat(timespec="seconds")
    db_execute(
        conn,
        """
        INSERT INTO events (
            storage_key, server_sid, server_name, property_type, event_type,
            old_owner, new_owner, building, apt_name, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            storage,
            server_sid,
            server_name,
            property_type,
            event_type,
            old_owner,
            new_owner,
            building,
            apt_name,
            now,
        ),
    )


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    db_execute(
        conn,
        """
        INSERT INTO meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def send_telegram(token: str, chat_ids: list[str | int], text: str) -> None:
    for chat_id in chat_ids:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if not resp.ok or not body.get("ok"):
            desc = body.get("description", resp.text or resp.reason)
            hint = ""
            if "chat not found" in str(desc).lower():
                hint = (
                    " Открой бота в Telegram, нажми /start, "
                    "узнай chat_id через @userinfobot."
                )
            raise RuntimeError(
                f"Telegram sendMessage (chat {chat_id}): {desc}.{hint}"
            ) from None


def verify_telegram(token: str, chat_ids_raw: list[str]) -> list[str | int]:
    me = requests.get(
        f"https://api.telegram.org/bot{token}/getMe",
        timeout=30,
    ).json()
    if not me.get("ok"):
        raise RuntimeError(f"Неверный TELEGRAM_BOT_TOKEN: {me}")

    username = me["result"].get("username", "?")
    verified: list[str | int] = []
    for raw in chat_ids_raw:
        chat_id = parse_chat_id(raw)
        test = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "✅ Бот подключён. Мониторинг слётов запускается…",
                "disable_web_page_preview": True,
            },
            timeout=30,
        ).json()
        if not test.get("ok"):
            desc = test.get("description", "unknown error")
            raise RuntimeError(
                f"Не могу писать в chat_id={raw!r} ({desc}).\n"
                f"1) Открой @{username} → Start (/start)\n"
                f"2) Id в TELEGRAM_CHAT_IDS через запятую"
            )
        verified.append(chat_id)
    ids = ", ".join(str(c) for c in verified)
    log.info("Telegram OK (@%s → %s чат(ов): %s)", username, len(verified), ids)
    return verified


def _price_line(item: dict) -> str:
    price = item.get("price")
    if not price:
        return ""
    return f"\nЦена: {price:,} $".replace(",", " ")


def _kind_label(item: dict) -> tuple[str, str]:
    if item.get("kind") == "house":
        return "🏠 Дом", "Дом"
    return "🚪 Квартира", "Квартира"


def format_slet_message(server_name: str, item: dict, former_owner: str) -> str:
    now = datetime.now(MSK).strftime("%d.%m.%Y %H:%M:%S")
    icon, label = _kind_label(item)
    return (
        f"🔴 СЛЕТ [{server_name}]\n"
        f"🕐 {now}\n\n"
        f"{icon}\n"
        f"{item['name']} · {item['class_name']}\n"
        f"👤 Бывший владелец: {former_owner}"
        f"{_price_line(item)}"
    )


def format_purchase_message(server_name: str, item: dict, new_owner: str) -> str:
    now = datetime.now(MSK).strftime("%d.%m.%Y %H:%M:%S")
    icon, _ = _kind_label(item)
    return (
        f"🟢 КУПИЛИ [{server_name}]\n"
        f"🕐 {now}\n\n"
        f"{icon}\n"
        f"{item['name']} · {item['class_name']}\n"
        f"👤 Новый владелец: {new_owner}"
        f"{_price_line(item)}"
    )


def _process_properties(
    conn: sqlite3.Connection,
    server_sid: str,
    server_name: str,
    items: list[dict],
    kind: str,
    token: str,
    chat_ids: list[str | int],
    *,
    notify_purchase: bool,
) -> dict[str, int]:
    first_run = not is_part_initialized(conn, server_sid, kind)
    slet_count = 0
    purchase_count = 0
    changed_count = 0

    for item in items:
        storage = storage_key(server_sid, kind, item["key"])
        owner = normalize_owner(item["owner"])
        prev = get_known_owner(conn, storage)
        if prev is None:
            prev = ""

        changed = prev != owner

        if not first_run and changed:
            if prev and not owner:
                send_telegram(
                    token,
                    chat_ids,
                    format_slet_message(server_name, item, prev),
                )
                log_event(
                    conn,
                    storage,
                    server_sid,
                    server_name,
                    kind,
                    "slet",
                    prev,
                    "",
                    item["building"],
                    item["name"],
                )
                kind_ru = "дом" if kind == "house" else "кв."
                log.info(
                    "[%s] СЛЕТ %s: %s — %s",
                    server_name,
                    kind_ru,
                    item["name"],
                    prev,
                )
                slet_count += 1
            elif not prev and owner:
                after_slet = is_awaiting_purchase(conn, storage)
                if after_slet and notify_purchase:
                    send_telegram(
                        token,
                        chat_ids,
                        format_purchase_message(server_name, item, owner),
                    )
                if after_slet:
                    log_event(
                        conn,
                        storage,
                        server_sid,
                        server_name,
                        kind,
                        "purchase",
                        "",
                        owner,
                        item["building"],
                        item["name"],
                    )
                    kind_ru = "дом" if kind == "house" else "кв."
                    log.info(
                        "[%s] КУПИЛИ %s: %s — %s",
                        server_name,
                        kind_ru,
                        item["name"],
                        owner,
                    )
                    purchase_count += 1
            elif prev and owner:
                set_awaiting_purchase(conn, storage, False)

        upsert_property(conn, storage, server_sid, server_name, item, owner)
        if not first_run and changed:
            if prev and not owner:
                set_awaiting_purchase(conn, storage, True)
            elif not prev and owner:
                set_awaiting_purchase(conn, storage, False)
        if changed or first_run:
            changed_count += 1

    if first_run and items:
        set_part_initialized(conn, server_sid, kind)
        label = "домов" if kind == "house" else "квартир"
        log.debug("[%s] Первый снимок: %s %s", server_name, len(items), label)

    return {
        "count": len(items),
        "changed": changed_count,
        "slet": slet_count,
        "purchase": purchase_count,
        "first_run": int(first_run and bool(items)),
    }


def check_server_from_data(
    conn: sqlite3.Connection,
    server_sid: str,
    server_name: str,
    data: dict,
    token: str,
    chat_ids: list[str | int],
    *,
    notify_purchase: bool,
) -> dict[str, int]:
    apartments = list(iter_apartments(data))
    apt_stats = _process_properties(
        conn,
        server_sid,
        server_name,
        apartments,
        "apt",
        token,
        chat_ids,
        notify_purchase=notify_purchase,
    )
    return {
        "apartments": apt_stats["count"],
        "houses": 0,
        "changed": apt_stats["changed"],
        "slet": apt_stats["slet"],
        "purchase": apt_stats["purchase"],
        "first_run": apt_stats["first_run"],
    }


def _fetch_catalog_safe(server_sid: str, server_name: str) -> dict | None:
    try:
        return fetch_catalog(server_sid)
    except Exception:
        log.exception("[%s] Ошибка загрузки с вики", server_name)
        return None


def check_all_servers(
    conn: sqlite3.Connection,
    servers: list[tuple[str, str]],
    token: str,
    chat_ids: list[str | int],
    *,
    notify_purchase: bool,
) -> dict[str, int]:
    total_slet = 0
    total_purchase = 0
    total_changed = 0
    total_apartments = 0
    total_houses = 0
    any_first = False

    workers = min(8, max(1, len(servers)))
    fetched: list[tuple[str, str, dict]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_server = {
            pool.submit(_fetch_catalog_safe, server_sid, server_name): (
                server_sid,
                server_name,
            )
            for server_sid, server_name in servers
        }
        for fut in as_completed(future_to_server):
            server_sid, server_name = future_to_server[fut]
            data = fut.result()
            if data is not None:
                fetched.append((server_sid, server_name, data))

    for server_sid, server_name, data in fetched:
        stats = check_server_from_data(
            conn,
            server_sid,
            server_name,
            data,
            token,
            chat_ids,
            notify_purchase=notify_purchase,
        )

        total_apartments += stats["apartments"]
        total_houses += stats["houses"]
        total_changed += stats["changed"]
        total_slet += stats["slet"]
        total_purchase += stats["purchase"]
        if stats["first_run"]:
            any_first = True

        conn.commit()

        if not stats["first_run"]:
            log.debug(
                "[%s] OK — %s кв., изменений: %s",
                server_name,
                stats["apartments"],
                stats["changed"],
            )

    conn.commit()
    set_meta(conn, "last_check_at", datetime.now(MSK).isoformat(timespec="seconds"))

    if any_first and not startup_sent(conn):
        counts = count_db_properties(conn)
        send_telegram(
            token,
            chat_ids,
            (
                f"✅ Мониторинг запущен\n"
                f"Серверов: {len(servers)}\n"
                f"В базе: {counts['apt']} квартир\n"
                f"Проверка: каждые {check_interval_sec()} сек\n"
                f"🔴 слёт в гос · 🟢 покупка из гос"
            ),
        )
        set_startup_sent(conn)
        conn.commit()

    if total_slet or total_purchase:
        log.info(
            "Итог — слётов: %s, покупок: %s",
            total_slet,
            total_purchase,
        )
    else:
        log.debug(
            "Итог — изменений: %s (слётов: 0, покупок: 0)",
            total_changed,
        )

    return {
        "slet": total_slet,
        "purchase": total_purchase,
        "changed": total_changed,
        "apartments": total_apartments,
        "servers_ok": len(fetched),
        "servers_total": len(servers),
    }


def check_interval_sec() -> float:
    raw = os.environ.get("CHECK_INTERVAL_SEC", "15").strip()
    try:
        sec = float(raw)
    except ValueError:
        sec = 15.0
    return max(5.0, sec)


def status_log_sec() -> float:
    raw = os.environ.get("STATUS_LOG_MIN", "10").strip()
    try:
        minutes = float(raw)
    except ValueError:
        minutes = 10.0
    return max(1.0, minutes) * 60.0


def log_period_status(
    conn: sqlite3.Connection,
    servers: list[tuple[str, str]],
    *,
    period_slet: int,
    period_purchase: int,
    cycles_ok: int,
    cycles_fail: int,
    minutes: float,
) -> None:
    counts = count_db_properties(conn)
    names = ", ".join(n for _, n in servers)
    log.info(
        "Статус за %.0f мин — слётов: %s, покупок: %s | "
        "циклов OK: %s, ошибок: %s | в базе %s кв. | серверы: %s",
        minutes,
        period_slet,
        period_purchase,
        cycles_ok,
        cycles_fail,
        counts["apt"],
        names,
    )


def main() -> None:
    load_env_file()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids_raw = resolve_chat_ids()
    notify_purchase = os.environ.get("NOTIFY_PURCHASE", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    if not token or not chat_ids_raw:
        log.error(
            "Задай TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_IDS (или TELEGRAM_CHAT_ID) в .env"
        )
        sys.exit(1)

    try:
        servers = resolve_servers()
    except RuntimeError as exc:
        log.error("%s", exc)
        sys.exit(1)

    try:
        chat_ids = verify_telegram(token, chat_ids_raw)
    except RuntimeError as exc:
        log.error("%s", exc)
        sys.exit(1)

    acquire_instance_lock()
    try:
        conn = open_db()
    except RuntimeError as exc:
        log.error("%s", exc)
        sys.exit(1)
    init_db(conn)

    interval = check_interval_sec()
    status_every = status_log_sec()
    status_min = status_every / 60.0
    server_list = ", ".join(f"{sid} {name}" for sid, name in servers)
    log.info(
        "Старт: %s сервер(ов) — %s | только квартиры, интервал %s сек, "
        "статус в терминал каждые %.0f мин",
        len(servers),
        server_list,
        int(interval) if interval == int(interval) else interval,
        status_min,
    )
    if len(servers) >= len(ALL_SERVERS):
        log.warning(
            "GTA5RP_SERVER_SIDS=all — слёты со ВСЕХ серверов. "
            "Чтобы только нужные: GTA5RP_SERVER_SIDS=20 или 20,21,24"
        )

    period_slet = 0
    period_purchase = 0
    cycles_ok = 0
    cycles_fail = 0
    last_status = time.monotonic()

    while True:
        started = time.monotonic()
        try:
            stats = check_all_servers(
                conn,
                servers,
                token,
                chat_ids,
                notify_purchase=notify_purchase,
            )
            cycles_ok += 1
            period_slet += stats["slet"]
            period_purchase += stats["purchase"]
        except Exception:
            cycles_fail += 1
            conn.rollback()
            log.exception("Ошибка цикла проверки")

        now = time.monotonic()
        if now - last_status >= status_every:
            log_period_status(
                conn,
                servers,
                period_slet=period_slet,
                period_purchase=period_purchase,
                cycles_ok=cycles_ok,
                cycles_fail=cycles_fail,
                minutes=status_min,
            )
            period_slet = 0
            period_purchase = 0
            cycles_ok = 0
            cycles_fail = 0
            last_status = now

        delay = max(0.0, interval - (time.monotonic() - started))
        log.debug("Пауза %.1f сек до следующего цикла", delay)
        time.sleep(delay)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Остановлено (Ctrl+C) — это нормально")
        sys.exit(0)
