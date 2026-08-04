"""What the model is asked to return, and what the graph is allowed to believe."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class Intent(enum.StrEnum):
    CREATE_TASK = "create_task"
    LIST_TASKS = "list_tasks"
    COMPLETE_TASK = "complete_task"
    SMALLTALK = "smalltalk"


class ParsedMessage(BaseModel):
    """One structured LLM call returns the intent and the task fields together.

    Task fields are meaningful only for `create_task`; the model regularly invents
    them for the other intents, so they are dropped here rather than trusted
    downstream.
    """

    model_config = ConfigDict(extra="ignore")

    intent: Intent
    title: str | None = None
    category: str | None = None
    due_at: datetime | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None

    @model_validator(mode="after")
    def drop_task_fields_unless_creating(self) -> ParsedMessage:
        if self.intent is not Intent.CREATE_TASK:
            self.title = None
            self.category = None
            self.due_at = None
            self.needs_clarification = False
            self.clarification_question = None
        return self

    @model_validator(mode="after")
    def a_clarification_needs_a_question(self) -> ParsedMessage:
        # Asking without a question would strand the dialog, so an unusable
        # answer is treated as no ambiguity at all.
        if self.needs_clarification and not self.clarification_question:
            self.needs_clarification = False
        return self
