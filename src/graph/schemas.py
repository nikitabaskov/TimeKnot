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


class Resolution(enum.StrEnum):
    """How a task is being closed. `cancelled` means it stopped being needed."""

    DONE = "done"
    CANCELLED = "cancelled"


class ParsedMessage(BaseModel):
    """One structured LLM call returns the intent and every field it may carry.

    Each intent owns a different subset. The model regularly fills in fields that
    belong to another intent, so everything outside the current one is dropped
    here rather than trusted downstream.
    """

    model_config = ConfigDict(extra="ignore")

    intent: Intent
    # create_task
    title: str | None = None
    category: str | None = None
    due_at: datetime | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    # complete_task
    target: str | None = None
    resolution: Resolution = Resolution.DONE
    # smalltalk
    smalltalk_reply: str | None = None

    @model_validator(mode="after")
    def keep_only_the_fields_of_this_intent(self) -> ParsedMessage:
        if self.intent is not Intent.CREATE_TASK:
            self.title = None
            self.category = None
            self.due_at = None
            self.needs_clarification = False
            self.clarification_question = None
        if self.intent is not Intent.COMPLETE_TASK:
            self.target = None
            self.resolution = Resolution.DONE
        if self.intent is not Intent.SMALLTALK:
            self.smalltalk_reply = None
        return self

    @model_validator(mode="after")
    def a_clarification_needs_a_question(self) -> ParsedMessage:
        # Asking without a question would strand the dialog, so an unusable
        # answer is treated as no ambiguity at all.
        if self.needs_clarification and not self.clarification_question:
            self.needs_clarification = False
        return self
