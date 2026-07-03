"""Тесты парсера времени сборов."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from gatherings.service import GatherTimeParseError, parse_gathering_time


def _fixed_now() -> datetime:
    return datetime(2026, 4, 8, 14, 30, tzinfo=datetime.now().astimezone().tzinfo)


@patch("gatherings.service.datetime")
def test_timer_minutes(mock_dt):
    mock_dt.now.return_value = _fixed_now()
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

    mode, ends_at, hint = parse_gathering_time("15")

    assert mode == "timer"
    assert hint == "15 мин"
    assert ends_at == int((_fixed_now() + timedelta(minutes=15)).timestamp())


@pytest.mark.parametrize("raw", ["15:00", "15 00", "15-00"])
@patch("gatherings.service.datetime")
def test_clock_time(mock_dt, raw):
    mock_dt.now.return_value = _fixed_now()
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

    mode, ends_at, hint = parse_gathering_time(raw)

    assert mode == "clock"
    assert hint == "15:00"
    target = _fixed_now().replace(hour=15, minute=0, second=0, microsecond=0)
    assert ends_at == int(target.timestamp())


@patch("gatherings.service.datetime")
def test_clock_next_day_if_passed(mock_dt):
    mock_dt.now.return_value = _fixed_now().replace(hour=16, minute=0)
    mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

    mode, ends_at, hint = parse_gathering_time("15:00")

    assert mode == "clock"
    assert hint == "15:00"
    target = mock_dt.now.return_value.replace(
        hour=15, minute=0, second=0, microsecond=0,
    ) + timedelta(days=1)
    assert ends_at == int(target.timestamp())


@pytest.mark.parametrize("raw", ["", "abc", "25:00", "15 0", "-5"])
def test_invalid(raw):
    with pytest.raises(GatherTimeParseError):
        parse_gathering_time(raw)
