"""Shared fixtures. The database is real; only the clock is faked."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from repositories.database import build_engine, build_session_factory, create_schema
from services.tasks import TaskService

OWNER_ID = 111
TIMEZONE = "Asia/Krasnoyarsk"
NOW = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self, now: datetime = NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = build_engine(tmp_path / "timeknot.db")
    await create_schema(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return build_session_factory(engine)


@pytest.fixture
async def session(session_factory: async_sessionmaker) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def task_service(session_factory: async_sessionmaker, clock: FixedClock) -> TaskService:
    return TaskService(session_factory=session_factory, clock=clock, default_timezone=TIMEZONE)


class MessageSpy:
    """Stands in for an aiogram Message: records what the user would have seen."""

    def __init__(self, user_id: int = OWNER_ID, text: str = "test message") -> None:
        self.from_user = type("User", (), {"id": user_id})()
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)
