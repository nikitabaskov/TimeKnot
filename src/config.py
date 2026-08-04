"""Application configuration read from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Krasnoyarsk"
DEFAULT_DATABASE_PATH = "timeknot.db"


class ConfigError(Exception):
    """Raised when the environment does not describe a runnable application."""


@dataclass(frozen=True, slots=True)
class Config:
    telegram_bot_token: str
    owner_user_ids: frozenset[int]
    timezone: str
    database_path: Path


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Build a Config or raise ConfigError with a message a human can act on."""
    source = os.environ if env is None else env

    token = source.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "TELEGRAM_BOT_TOKEN is not set. Put the token from @BotFather into the environment "
            "(see .env.example)."
        )

    raw_ids = source.get("OWNER_USER_IDS", "").strip()
    if not raw_ids:
        raise ConfigError(
            "OWNER_USER_IDS is not set. List the Telegram user ids allowed to use the bot, "
            "comma-separated (see .env.example)."
        )

    owner_user_ids = set()
    for chunk in raw_ids.split(","):
        item = chunk.strip()
        if not item:
            continue
        try:
            owner_user_ids.add(int(item))
        except ValueError:
            raise ConfigError(
                f"OWNER_USER_IDS contains {item!r}, which is not a Telegram user id. "
                "Expected comma-separated integers, e.g. 12345678,87654321."
            ) from None

    if not owner_user_ids:
        raise ConfigError(
            "OWNER_USER_IDS is empty after parsing; at least one user id is required."
        )

    timezone = source.get("TIMEZONE", "").strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(
            f"TIMEZONE is set to {timezone!r}, which is not an IANA timezone name. "
            f"Expected something like {DEFAULT_TIMEZONE}."
        ) from None

    database_path = source.get("DATABASE_PATH", "").strip() or DEFAULT_DATABASE_PATH

    return Config(
        telegram_bot_token=token,
        owner_user_ids=frozenset(owner_user_ids),
        timezone=timezone,
        database_path=Path(database_path),
    )
