"""The Telegram side of the reminder sender port."""

from __future__ import annotations

from aiogram import Bot


class TelegramSender:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send(self, *, user_id: int, text: str) -> None:
        await self._bot.send_message(chat_id=user_id, text=text)
