"""The extraction prompt.

Relative dates are resolved by the model, so it must be told what "now" is —
in local time, with the weekday spelled out.
"""

from __future__ import annotations

from datetime import datetime

WEEKDAYS = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)

_TEMPLATE = """\
Ты разбираешь сообщения владельца личного ассистента задач. Отвечай только JSON-объектом.

Сейчас: {local_now} ({weekday}), часовой пояс {offset}.

Поля JSON:
- intent — одно из: create_task, list_tasks, complete_task, smalltalk.
  create_task — просят завести дело или напоминание.
  list_tasks — спрашивают, что запланировано.
  complete_task — сообщают, что дело сделано или больше не нужно.
  smalltalk — приветствие, благодарность, всё остальное.
- title — суть дела короткой фразой, без слов о времени. Только при create_task, иначе null.
- category — одно слово по смыслу дела (покупки, работа, здоровье, дом, ...) или null.
- due_at — абсолютный момент в формате ISO-8601 со смещением, например 2026-08-05T19:00:00{offset}.
  Только при create_task. Если времени в сообщении нет — null.
- needs_clarification — true, только если время названо, но двусмысленно и догадка рискует
  промахнуться на полсуток («напомни в 5» — утра или вечера?). Отсутствие времени вовсе
  двусмысленностью не считается.
- clarification_question — короткий вопрос владельцу, если needs_clarification true, иначе null.
- target — при complete_task: суть дела, о котором говорит владелец, его словами и без слов
  «сделал», «закрой», «отмени». Иначе null.
- resolution — при complete_task: done, если дело выполнено; cancelled, если оно отпало и больше
  не нужно. Иначе done.
- smalltalk_reply — при smalltalk: короткий дружелюбный ответ одной фразой. Иначе null.

Правила для due_at:
- Относительные выражения («через 45 минут», «завтра», «в следующую среду») считай сам от «сейчас».
- Расплывчатое время суток переводи в час: утро — 09:00, день — 14:00, вечер — 19:00, ночь — 23:00.
- Время без части суток трактуй как ближайшее будущее.
- Никогда не возвращай относительное выражение текстом — только абсолютный момент.
"""

_CLARIFICATION_TEMPLATE = """\
Ранее владелец написал: «{original}»
Ты спросил: «{question}»
Владелец ответил: «{answer}»

Если ответ уточняет время — верни ту же задачу с точным due_at.
Если ответ не про время, а про что-то своё — разбери его как обычное новое сообщение и забудь
про прежнюю задачу.
Второй раз переспрашивать нельзя: needs_clarification всегда false. Если ясности так и нет,
верни create_task с due_at = null.
"""


def build_system_prompt(local_now: datetime) -> str:
    """Build the system prompt for a given local moment."""
    offset = local_now.strftime("%z")
    return _TEMPLATE.format(
        local_now=local_now.strftime("%Y-%m-%d %H:%M"),
        weekday=WEEKDAYS[local_now.weekday()],
        offset=f"{offset[:3]}:{offset[3:]}",
    )


def build_clarification_prompt(
    local_now: datetime, *, original: str, question: str, answer: str
) -> str:
    """The follow-up prompt, carrying the exchange that led to it.

    The answer is re-parsed as a whole message rather than as a time fragment, so
    a user who changed the subject is followed instead of being trapped.
    """
    return (
        build_system_prompt(local_now)
        + "\n"
        + _CLARIFICATION_TEMPLATE.format(original=original, question=question, answer=answer)
    )
