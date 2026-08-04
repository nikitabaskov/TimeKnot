# 05 — Напоминание срабатывает

**What to build:** Владелец создаёт задачу на «через две минуты» и через две минуты получает от бота сообщение. Пока процесс жив, напоминания приходят вовремя.

**Blocked by:** 04 — Живой разбор текста и создание задачи.

**Status:** done

- [x] APScheduler на `AsyncIOScheduler` с `MemoryJobStore`; персистентный jobstore не используется
- [x] Создание задачи со сроком ставит джоб; таблица `tasks` остаётся единственным источником правды
- [x] Шов `dispatch_due` принимает текущий момент и возвращает отправленные напоминания
- [x] Отправитель Telegram описан протоколом и подменяется в тестах
- [x] Статус переводится **после** успешной отправки: доставка at-least-once, дубликат допустим, пропуск — нет
- [x] Перед отправкой статус задачи перечитывается из БД; по закрытой задаче напоминание не уходит
- [x] Задача с пустым `due_at` в планировщик не попадает
- [x] Тесты гоняют `dispatch_due` на фиксированных часах

## Comments

- `ReminderSender` and `ReminderPlanner` are protocols in top-level `reminders.py`, outside every
  layer, so `services` can depend on them without importing `scheduler` or `bot`.
- The re-read of the status before sending *is* the `list_due` query: it filters on
  `status = pending` at dispatch time, so a task closed after its job was armed is never selected.
- `reminder_sent_at IS NULL` is part of that query. Without it every dispatch would resend
  everything already delivered.
- The job is armed after the commit, and only for a task that has a `due_at`.
- APScheduler applies `replace_existing` only while running; a stopped scheduler just queues jobs
  and would silently give a rescheduled task a second timer. `schedule()` now refuses to run
  before `start()` rather than let that happen.
- The fire callback dispatches for `max(clock.now(), scheduled_for)`: a timer firing a hair early
  would otherwise miss its own `due_at <= now` window.
- A failing send is logged and skipped, leaving the task unmarked; one unreachable chat must not
  hold up the other reminders.
- Rehydration on startup is ticket 06, the inline buttons are ticket 07.
