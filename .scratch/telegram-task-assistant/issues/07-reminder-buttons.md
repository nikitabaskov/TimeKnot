# 07 — Кнопки «Завершено» и «Отложить на 1 час»

**What to build:** Под напоминанием две кнопки. «Завершено» закрывает задачу, она пропадает из `/tasks` и больше не напоминает о себе. «Отложить на 1 час» сдвигает напоминание и присылает его снова через час.

**Blocked by:** 05 — Напоминание срабатывает.

**Status:** done

- [x] Напоминание уходит с inline-клавиатурой из двух кнопок
- [x] «Завершено» переводит задачу в `done`; сообщение обновляется, кнопки убираются
- [x] «Отложить на 1 час» сдвигает `due_at` на час, оставляет статус `pending` и перепланирует джоб
- [x] Шаг откладывания фиксированный, выбора интервала нет
- [x] Повторное нажатие на устаревшую кнопку не ломает состояние и не создаёт дубль
- [x] `/tasks` показывает только `pending`
- [x] Тесты через шов callback-обработки: проверяются статус в БД и состав отправленного

## Comments

- `ReminderSender.send` gained a `task_id`, so the transport can build the keyboard without
  `services` learning what a Telegram keyboard is.
- Snoozing clears `reminder_sent_at`. Without that the moved reminder would be treated as already
  delivered and never go out again — the one bug that would have made the button useless.
- The new moment is `max(due_at, now) + 1 hour`. On a normal press the two agree; after downtime a
  caught-up reminder is hours overdue, and `due_at + 1h` could land in the past, firing again
  instantly. The ticket's own wording ("присылает его снова через час") is what this honours.
- A stale press answers with a notice and changes nothing: neither status, nor `due_at`, nor the
  timer. Ownership is checked too, so a task id belonging to someone else reads as missing.
- The keyboard disappears because the message text is replaced without one, so the same button
  cannot be pressed twice from the same message.
