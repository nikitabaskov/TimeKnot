"""Dialog state persistence.

The checkpointer lives in the same SQLite file as the tasks: one file to back up,
and no second database to keep in sync.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


@asynccontextmanager
async def open_checkpointer(database_path: Path) -> AsyncIterator[AsyncSqliteSaver]:
    async with aiosqlite.connect(str(database_path)) as connection:
        saver = AsyncSqliteSaver(connection)
        await saver.setup()
        yield saver
