"""Composition root: build the aiogram application from a Config."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot import handlers
from bot.filters import OwnerOnly
from config import Config


def build_dispatcher(config: Config) -> Dispatcher:
    dispatcher = Dispatcher()
    owner_only = OwnerOnly(config.owner_user_ids)
    dispatcher.message.filter(owner_only)
    dispatcher.callback_query.filter(owner_only)
    dispatcher.include_router(handlers.router)
    return dispatcher


def build_bot(config: Config) -> Bot:
    return Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def run_polling(config: Config) -> None:
    bot = build_bot(config)
    dispatcher = build_dispatcher(config)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
