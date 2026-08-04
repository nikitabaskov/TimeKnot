# 02 — Хранилище задач и пустой `/tasks`

**What to build:** Владелец вызывает `/tasks` и получает ответ «список пуст». Сквозной путь от команды Telegram через сценарий и репозиторий до SQLite работает целиком, хотя задач ещё никто не создаёт.

**Blocked by:** 01 — Каркас проекта и живой бот.

**Status:** done

- [x] Таблица `users`: первичный ключ — Telegram user id, поле часового пояса; строка владельца создаётся при первом обращении
- [x] Таблица `tasks`: `user_id` (FK на `users`), заголовок, категория, `due_at` (nullable), статус, `rrule` (всегда NULL), метки создания и отправки напоминания
- [x] Статусы ограничены значениями `pending`, `done`, `cancelled`
- [x] Все моменты времени пишутся и читаются в UTC
- [x] Часовой пояс по умолчанию — `Asia/Krasnoyarsk` (UTC+7), берётся из переменной окружения
- [x] Доступ к данным только через репозиторий; сценарии не знают про SQLAlchemy
- [x] Схема создаётся при старте на пустой БД без ручных шагов
- [x] `/tasks` на пустой базе отвечает «список пуст»
- [x] Тесты идут против настоящей SQLite во временном файле, новой на каждый тест

## Comments

Implemented in `6ad6093`.

- `UtcDateTime` (a `TypeDecorator`) raises on naive datetimes and returns aware UTC on read.
  Without it SQLite silently drops the timezone.
- `Enum(create_constraint=True)` is required — the flag defaults to `False` in SQLAlchemy 2, so
  the `status` column would otherwise be an unconstrained VARCHAR.
- SQLite ignores foreign keys unless `PRAGMA foreign_keys=ON` runs on every connection; wired to
  the engine `connect` event.
- The clock protocol landed here rather than in 03: creating the owner row needs a current moment.
