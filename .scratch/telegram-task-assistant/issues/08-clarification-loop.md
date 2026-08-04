# 08 — Уточняющий диалог

**What to build:** Владелец пишет «напомни в 5», бот спрашивает «5 утра или 5 вечера?». Владелец отвечает обычным текстом — задача создаётся на нужный час. Если между вопросом и ответом бот перезапустили, диалог всё равно продолжается с той же точки.

**Blocked by:** 04 — Живой разбор текста и создание задачи.

**Status:** done

- [x] Состояние графа персистится в `AsyncSqliteSaver` в том же файле БД, `thread_id = chat_id`
- [x] Двусмысленное время останавливает граф через `interrupt` и отправляет вопрос
- [x] Следующее сообщение пользователя возобновляет граф с точки остановки
- [x] Уточнение задаётся не более одного раза на задачу; если ясности нет — задача сохраняется без срока, пользователю это сообщается
- [x] Пользователь может бросить уточнение, написав что-то другое, и не застрять в диалоге
- [x] Отдельного FSM в aiogram нет: состояние диалога хранится только в чекпойнтере
- [x] Тест на рестарт: чекпойнтер переоткрывается новым экземпляром, диалог продолжается

## Comments

- `AsyncSqliteSaver` runs over its own `aiosqlite` connection to the same file the tasks live in;
  verified that `checkpoints`, `writes`, `tasks` and `users` share one database.
- `thread_id` is the Telegram user id. For a private bot the chat and the user are the same.
- The resume decision is read from the checkpointer (`aget_state(...).next`), not from any bot-side
  state — there is no aiogram FSM anywhere.
- Walking away is handled by re-parsing rather than by pattern matching: the answer goes back to
  the model together with the original message and the question, and if it turns out to be a new
  message the graph simply follows its intent. Nothing traps the owner in the dialog.
- One question per task is enforced twice: `extract_after_clarification` blanks the flag whatever
  the model says, and the router refuses `clarify` once `clarified` is set. If the time is still
  unknown the task is stored undated and the reply says so.
- `needs_clarification` without a question text is downgraded to "no ambiguity" in the schema —
  interrupting with an empty question would strand the dialog.
