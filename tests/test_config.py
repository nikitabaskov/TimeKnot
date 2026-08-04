"""A missing or malformed environment must fail loudly and understandably."""

from __future__ import annotations

from pathlib import Path

import pytest

from config import DEFAULT_DATABASE_PATH, DEFAULT_TIMEZONE, ConfigError, load_config

VALID_ENV = {"TELEGRAM_BOT_TOKEN": "123:abc", "OWNER_USER_IDS": "111"}


def test_loads_token_and_owners() -> None:
    config = load_config({"TELEGRAM_BOT_TOKEN": "123:abc", "OWNER_USER_IDS": "111, 222"})
    assert config.telegram_bot_token == "123:abc"
    assert config.owner_user_ids == frozenset({111, 222})


@pytest.mark.parametrize("missing", ["TELEGRAM_BOT_TOKEN", "OWNER_USER_IDS"])
def test_missing_variable_is_reported_by_name(missing: str) -> None:
    env = {key: value for key, value in VALID_ENV.items() if key != missing}
    with pytest.raises(ConfigError, match=missing):
        load_config(env)


def test_non_numeric_owner_id_is_reported() -> None:
    with pytest.raises(ConfigError, match="OWNER_USER_IDS"):
        load_config({**VALID_ENV, "OWNER_USER_IDS": "111,me"})


def test_timezone_and_database_path_have_defaults() -> None:
    config = load_config(VALID_ENV)
    assert config.timezone == DEFAULT_TIMEZONE == "Asia/Krasnoyarsk"
    assert config.database_path == Path(DEFAULT_DATABASE_PATH)


def test_timezone_and_database_path_are_overridable() -> None:
    config = load_config({**VALID_ENV, "TIMEZONE": "Europe/Moscow", "DATABASE_PATH": "/data/db"})
    assert config.timezone == "Europe/Moscow"
    assert config.database_path == Path("/data/db")


def test_unknown_timezone_is_reported() -> None:
    with pytest.raises(ConfigError, match="TIMEZONE"):
        load_config({**VALID_ENV, "TIMEZONE": "Mars/Olympus"})
