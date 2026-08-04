"""Access control: the bot serves its owners and nobody else."""

from __future__ import annotations

from collections.abc import Iterable

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message


class OwnerOnly(Filter):
    """Passes only updates authored by a whitelisted Telegram user id.

    Registered on the dispatcher so that strangers are dropped silently before
    any handler, service or LLM call sees their text.
    """

    def __init__(self, owner_user_ids: Iterable[int]) -> None:
        self.owner_user_ids = frozenset(owner_user_ids)

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return user is not None and user.id in self.owner_user_ids
