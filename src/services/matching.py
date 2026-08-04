"""Finding which task the owner meant when they wrote "сделал корм коту".

Deterministic on purpose: a second LLM call to pick a row would double the
latency of every closing message, and a wrong pick closes the wrong task.
"""

from __future__ import annotations

import re

from repositories.models import Task

# Russian inflects endings heavily ("цветы" / "цветок" / "цветам"), so words are
# compared by their stem-ish prefix rather than in full.
STEM_LENGTH = 4
_WORD = re.compile(r"\w+", re.UNICODE)

# Words that carry no information about which task is meant.
STOPWORDS = frozenset(
    {
        "сделал",
        "сделала",
        "сделано",
        "готово",
        "выполнил",
        "выполнила",
        "закрой",
        "закрыть",
        "отмени",
        "отменить",
        "убери",
        "удали",
        "уже",
        "это",
        "того",
        "про",
        "для",
        "and",
    }
)


def stems(text: str) -> set[str]:
    return {
        word[:STEM_LENGTH]
        for word in (match.group().casefold() for match in _WORD.finditer(text))
        if word not in STOPWORDS and len(word) > 2
    }


def find_matches(target: str, tasks: list[Task]) -> list[Task]:
    """Tasks that best match the phrase, or an empty list when nothing does.

    More than one result means a genuine tie: the caller must ask rather than
    guess.
    """
    wanted = stems(target)
    if not wanted:
        return []

    scored = [(len(wanted & stems(task.title)), task) for task in tasks]
    best = max((score for score, _task in scored), default=0)
    if best == 0:
        return []
    return [task for score, task in scored if score == best]
