"""The bot talks to Telegram through a configurable origin.

`api.telegram.org` has no AAAA record, so a host without IPv4 needs a dual-stack
relay in front of it. Nothing here reaches the network: building a `Bot` only
assembles URLs.
"""

from __future__ import annotations

from aiogram import Bot

from bot.app import build_bot
from config import Config, load_config

TOKEN = "123:abc"
BASE_ENV = {
    "TELEGRAM_BOT_TOKEN": TOKEN,
    "OWNER_USER_IDS": "111",
    "OPENROUTER_API_KEY": "sk-test",
    "OPENROUTER_MODEL": "deepseek/deepseek-chat",
}


def config_with(**overrides: str) -> Config:
    return load_config({**BASE_ENV, **overrides})


async def urls_of(bot: Bot) -> tuple[str, str]:
    api = bot.session.api
    try:
        return api.api_url(token=TOKEN, method="getUpdates"), api.file_url(
            token=TOKEN, path="photos/1.jpg"
        )
    finally:
        await bot.session.close()


async def test_without_a_relay_the_bot_calls_telegram_directly() -> None:
    method_url, file_url = await urls_of(build_bot(config_with()))

    assert method_url == "https://api.telegram.org/bot123:abc/getUpdates"
    assert file_url == "https://api.telegram.org/file/bot123:abc/photos/1.jpg"


async def test_a_relay_origin_reshapes_both_urls() -> None:
    """Files matter as much as methods: a half-configured relay is a silent bug."""
    bot = build_bot(config_with(TELEGRAM_API_ORIGIN="https://relay.workers.dev"))

    method_url, file_url = await urls_of(bot)

    assert method_url == "https://relay.workers.dev/bot123:abc/getUpdates"
    assert file_url == "https://relay.workers.dev/file/bot123:abc/photos/1.jpg"


async def test_the_path_the_relay_matches_is_the_path_the_bot_builds() -> None:
    """deploy/worker/src/index.js accepts /bot<token>/ and /file/bot<token>/."""
    method_url, file_url = await urls_of(
        build_bot(config_with(TELEGRAM_API_ORIGIN="https://relay.workers.dev"))
    )

    assert method_url.startswith(f"https://relay.workers.dev/bot{TOKEN}/")
    assert file_url.startswith(f"https://relay.workers.dev/file/bot{TOKEN}/")
