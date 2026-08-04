"""Composition root: build the aiogram application from a Config."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot import handlers
from bot.filters import OwnerOnly
from clock import Clock, SystemClock
from config import Config
from graph.openrouter import OpenRouterClient
from graph.runner import MessageHandler
from repositories.database import build_engine, build_session_factory, create_schema
from services.tasks import TaskService


def build_dispatcher(
    config: Config,
    task_service: TaskService,
    message_handler: MessageHandler,
    clock: Clock,
) -> Dispatcher:
    dispatcher = Dispatcher()
    owner_only = OwnerOnly(config.owner_user_ids)
    dispatcher.message.filter(owner_only)
    dispatcher.callback_query.filter(owner_only)
    dispatcher["task_service"] = task_service
    dispatcher["message_handler"] = message_handler
    dispatcher["clock"] = clock
    dispatcher["timezone"] = ZoneInfo(config.timezone)
    dispatcher.include_router(handlers.router)
    return dispatcher


def build_bot(config: Config) -> Bot:
    return Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def run_polling(config: Config) -> None:
    engine = build_engine(config.database_path)
    await create_schema(engine)
    clock = SystemClock()
    timezone = ZoneInfo(config.timezone)
    task_service = TaskService(
        session_factory=build_session_factory(engine),
        clock=clock,
        default_timezone=config.timezone,
    )
    llm = OpenRouterClient(
        api_key=config.openrouter_api_key,
        model=config.openrouter_model,
        base_url=config.openrouter_base_url,
    )
    message_handler = MessageHandler(llm, task_service, timezone)

    bot = build_bot(config)
    dispatcher = build_dispatcher(config, task_service, message_handler, clock)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await llm.aclose()
        await engine.dispose()
