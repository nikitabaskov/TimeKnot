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

Правила для due_at:
- Относительные выражения («через 45 минут», «завтра», «в следующую среду») считай сам от «сейчас».
- Расплывчатое время суток переводи в час: утро — 09:00, день — 14:00, вечер — 19:00, ночь — 23:00.
- Время без части суток трактуй как ближайшее будущее.
- Никогда не возвращай относительное выражение текстом — только абсолютный момент.
"""


def build_system_prompt(local_now: datetime) -> str:
    """Build the system prompt for a given local moment."""
    offset = local_now.strftime("%z")
    return _TEMPLATE.format(
        local_now=local_now.strftime("%Y-%m-%d %H:%M"),
        weekday=WEEKDAYS[local_now.weekday()],
        offset=f"{offset[:3]}:{offset[3:]}",
    )
