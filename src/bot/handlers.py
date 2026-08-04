"""aiogram handlers."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="commands")

START_TEXT = (
    "Привет! Я записываю задачи и напоминаю о них.\n\n"
    "Просто напиши, что нужно сделать, обычным сообщением:\n"
    "• «Купить корм коту завтра в 19:00»\n"
    "• «Напомни проверить PR через 45 минут»\n"
    "• «Почитать книгу» — без срока, просто в список\n\n"
    "Если время окажется непонятным, я переспрошу.\n"
    "В назначенный момент напишу первым — с кнопками «Завершено» "
    "и «Отложить на 1 час».\n\n"
    "Команды:\n"
    "/tasks — активные задачи\n"
    "/start — это сообщение"
)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer(START_TEXT)
