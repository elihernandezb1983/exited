"""Краткий вывод в терминал (BOT_VERBOSE=true — подробности)."""

from __future__ import annotations

import os


def verbose() -> bool:
    return os.getenv("BOT_VERBOSE", "").lower() in ("1", "true", "yes")


def info(msg: str) -> None:
    print(msg)


def detail(msg: str) -> None:
    if verbose():
        print(msg)
