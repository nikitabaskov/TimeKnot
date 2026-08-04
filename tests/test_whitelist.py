"""Strangers must be dropped before anything else looks at their message."""

from __future__ import annotations

import pytest
from aiogram.types import Message, User

from bot.filters import OwnerOnly

OWNER_ID = 111
STRANGER_ID = 222


def message_from(user_id: int | None) -> Message:
    user = None if user_id is None else User(id=user_id, is_bot=False, first_name="test")
    return Message.model_construct(message_id=1, from_user=user, text="/start")


@pytest.mark.parametrize(
    ("user_id", "expected"),
    [(OWNER_ID, True), (STRANGER_ID, False), (None, False)],
)
async def test_owner_only_filter(user_id: int | None, expected: bool) -> None:
    passes = await OwnerOnly({OWNER_ID})(message_from(user_id))
    assert passes is expected


async def test_owner_only_accepts_several_owners() -> None:
    owner_only = OwnerOnly([OWNER_ID, 333])
    assert await owner_only(message_from(333))
    assert not await owner_only(message_from(STRANGER_ID))
