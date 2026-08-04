# 06 — Переживание рестарта

**What to build:** Владелец ставит напоминание, процесс бота убивают и поднимают позже. Напоминание всё равно приходит: будущее — вовремя, просроченное — сразу при старте, с пометкой об опоздании.

Это свойство, ради которого таблица `tasks` объявлена единственным источником правды.

**Blocked by:** 05 — Напоминание срабатывает.

**Status:** done

- [x] На старте выбираются все `pending` с непустым `due_at`
- [x] На будущие моменты ставятся джобы
- [x] Просроченные отправляются немедленно, текст содержит пометку об опоздании
- [x] Задачи в статусе `done` и `cancelled` при регидратации игнорируются
- [x] Повторный старт без новых задач не рассылает напоминания заново
- [x] Тест: задачи записаны в БД, планировщик поднят на сдвинутых вперёд часах, проверяется состав отправленного

## Comments

- Rehydration is two existing pieces rather than a new query path: `dispatch_due(now)` catches up
  the past, `list_upcoming(now)` arms the future. `reminder_sent_at` already keeps a second boot
  quiet, so nothing extra was needed for that.
- Lateness is derived, not passed in: a reminder is announced as late when it goes out more than
  `LATE_AFTER` (1 minute) past its moment. A caller cannot forget the flag, and a timer firing on
  schedule never carries the marker.
- `rehydrate()` runs after `scheduler.start()` in `run_polling`, which is also what the
  scheduling guard from ticket 05 requires.
