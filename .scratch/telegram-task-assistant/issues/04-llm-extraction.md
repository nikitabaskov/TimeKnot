# 04 — Живой разбор текста и создание задачи

**What to build:** Владелец пишет «Купить корм коту завтра в 19:00» и получает подтверждение с распознанной сутью задачи и итоговой датой. Задача лежит в БД и видна в `/tasks`. Напоминание в назначенное время пока не приходит.

**Blocked by:** 03 — Граф и шов `handle_message` на фейковом LLM.

**Status:** done

- [x] Реальная реализация LLM-клиента: OpenRouter через OpenAI-совместимый интерфейс, идентификатор модели из переменной окружения
- [x] В промпт подаются текущие локальные дата, время и день недели
- [x] Модель возвращает абсолютный ISO-8601; относительные выражения («через 45 минут», «в следующую среду») разрешает она, детерминированного парсера дат в проекте нет
- [x] Полученный момент конвертируется в UTC и сохраняется
- [x] Сообщение без времени («почитать книгу») создаёт задачу с пустым `due_at`
- [x] Подтверждение показывает суть задачи и итоговую дату в локальном времени
- [x] `/tasks` показывает задачи со сроком и без срока раздельно
- [x] Тесты идут через шов `handle_message` с фейковым LLM; сеть в тестах не трогается

## Comments

- `extract()` is the evaluation seam from the spec: text plus the current moment in, a
  `ParsedMessage` out. The golden set (ticket 12) drives it directly.
- The OpenAI SDK is created with `max_retries=0`: ticket 10 owns the retry policy and silent
  SDK-level retries would double every attempt.
- A naive ISO moment from the model is read as local time rather than rejected — the prompt asks
  for an offset, models drop it regularly, and local time is what the user meant.
- Model output wrapped in a ``` fence is unwrapped before validation.
- `response_format={"type": "json_object"}` is requested. This is not the strict JSON-schema mode
  the spec declines to rely on; Pydantic validation remains the real guarantee.
- Rendering moved from `bot/rendering.py` to `rendering.py`: the graph builds the confirmation
  text and may not import the bot layer.
- Retries, past-date rejection and provider backoff stay in ticket 10 as specified.
