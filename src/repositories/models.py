"""ORM models. Every stored moment is UTC — see UtcDateTime."""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UtcDateTime(TypeDecorator[datetime]):
    """Stores aware datetimes as naive UTC and reads them back as aware UTC.

    SQLite has no timezone type, so without this the tz would silently vanish
    on write and the value would come back naive and ambiguous.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                f"Naive datetime {value!r} cannot be stored; pass an aware datetime "
                "(local time is only allowed at the boundaries)."
            )
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class TaskStatus(enum.StrEnum):
    PENDING = "pending"
    DONE = "done"
    CANCELLED = "cancelled"


def _status_values(enum_class: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_class]


class User(Base):
    """The bot owner. Degenerate today (one row), a real FK target from day one."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    timezone: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(64), default=None)
    due_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None, index=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            native_enum=False,
            length=16,
            values_callable=_status_values,
            validate_strings=True,
            # Off by default in SQLAlchemy 2; without it the allowed values would
            # only be enforced in Python, not in the database.
            create_constraint=True,
            name="task_status",
        ),
        default=TaskStatus.PENDING,
    )
    # Reserved for recurring reminders; always NULL in v1.
    rrule: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
