"""Application configuration read from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Krasnoyarsk"
DEFAULT_DATABASE_PATH = "timeknot.db"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TELEGRAM_API_ORIGIN = "https://api.telegram.org"


class ConfigError(Exception):
    """Raised when the environment does not describe a runnable application."""


@dataclass(frozen=True, slots=True)
class Config:
    telegram_bot_token: str
    telegram_api_origin: str
    owner_user_ids: frozenset[int]
    timezone: str
    database_path: Path
    openrouter_api_key: str
    openrouter_model: str
    openrouter_base_url: str


def load_config(env: Mapping[str, str] | None = None) -> Config:
    """Build a Config or raise ConfigError with a message a human can act on."""
    source = os.environ if env is None else env

    token = source.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError(
            "TELEGRAM_BOT_TOKEN is not set. Put the token from @BotFather into the environment "
            "(see .env.example)."
        )

    # Everything Telegram is reached through this origin. It exists because
    # api.telegram.org has no AAAA record: an IPv6-only host needs a dual-stack
    # relay in front of it. See deploy/worker/ and the README.
    api_origin = source.get("TELEGRAM_API_ORIGIN", "").strip() or DEFAULT_TELEGRAM_API_ORIGIN
    if not api_origin.startswith(("http://", "https://")):
        raise ConfigError(
            f"TELEGRAM_API_ORIGIN is set to {api_origin!r}, which is not a URL. "
            f"Expected the scheme and host of the relay only, e.g. {DEFAULT_TELEGRAM_API_ORIGIN}."
        )
    api_origin = api_origin.rstrip("/")

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

    openrouter_api_key = source.get("OPENROUTER_API_KEY", "").strip()
    if not openrouter_api_key:
        raise ConfigError(
            "OPENROUTER_API_KEY is not set. Create a key at openrouter.ai/keys and put it into "
            "the environment (see .env.example)."
        )

    openrouter_model = source.get("OPENROUTER_MODEL", "").strip()
    if not openrouter_model:
        raise ConfigError(
            "OPENROUTER_MODEL is not set. Pick a paid model id from openrouter.ai/models, "
            "e.g. deepseek/deepseek-chat. Free `:free` variants have daily limits and get "
            "withdrawn, which a reminder bot cannot rely on."
        )

    return Config(
        telegram_bot_token=token,
        telegram_api_origin=api_origin,
        owner_user_ids=frozenset(owner_user_ids),
        timezone=timezone,
        database_path=Path(database_path),
        openrouter_api_key=openrouter_api_key,
        openrouter_model=openrouter_model,
        openrouter_base_url=(
            source.get("OPENROUTER_BASE_URL", "").strip() or DEFAULT_OPENROUTER_BASE_URL
        ),
    )
