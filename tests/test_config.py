"""A missing or malformed environment must fail loudly and understandably."""

from __future__ import annotations

import pytest

from config import ConfigError, load_config

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
