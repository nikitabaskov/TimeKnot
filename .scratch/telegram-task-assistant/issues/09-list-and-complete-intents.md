# 09 — Просмотр и закрытие задач текстом

**What to build:** Владелец пишет «Что на сегодня?» и получает список — без команды. Пишет «сделал корм коту» — задача закрывается. Если текст подходит под несколько задач, бот переспрашивает, какую именно.

**Blocked by:** 04 — Живой разбор текста и создание задачи.

**Status:** done

- [x] Ветка `list_tasks` выдаёт тот же список, что и `/tasks`
- [x] Ветка `complete_task` находит задачу по смыслу текста и переводит её в `done`
- [x] Несколько подходящих задач — переспрос с выбором, автоматического закрытия не происходит
- [x] Ни одной подходящей — внятный ответ, что закрывать нечего
- [x] Ветка `smalltalk` отвечает коротко и не создаёт задачу
- [x] Возможность отмены задачи как ненужной (`cancelled`), отличимая от `done`
- [x] Тесты через шов `handle_message` на все ветки, включая переспрос

## Comments

- The `list_tasks` branch calls the same `TaskService.list_active` and the same renderer `/tasks`
  uses, so the two routes cannot drift apart.
- Matching a task by meaning is deterministic (`services/matching.py`), not a second LLM call: an
  extra round trip on every closing message would double the latency, and a wrong pick closes the
  wrong task. Words are compared by a four-character prefix, which is enough for Russian endings
  ("полил цветок" finds "Полить цветы"), and filler verbs are dropped.
- A tie interrupts the graph exactly like the clarifying dialog does — the runner already knows
  how to resume, so the re-ask needed no new machinery. The answer is read as a position or as
  words; an unusable answer closes nothing.
- Cancelling rides on `complete_task` as a `resolution` field rather than a fifth intent, since
  the spec fixes the intent vocabulary at four values.
- `smalltalk_reply` comes from the same single LLM call. A missing or empty one falls back to a
  constant, so the branch always answers.
