# 01 — Каркас проекта и живой бот

**What to build:** Владелец пишет боту `/start` в Telegram и получает ответ с описанием возможностей. Посторонний пишет то же самое и не получает ничего. Проект собирается и проверяется одной командой.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `uv sync`, `uv run pytest`, `uv run ruff check --fix . && uv run ruff format .` отрабатывают на чистом клоне
- [x] Бот поднимается в режиме long polling, токен и whitelist берутся из переменных окружения
- [x] `/start` отвечает текстом с описанием возможностей
- [x] Сообщение от `user_id` вне whitelist отбрасывается молча, до любой другой обработки
- [x] Отсутствие обязательной переменной окружения роняет запуск с внятным сообщением, а не с трейсбеком по `KeyError`
- [x] Есть тест на фильтр whitelist: разрешённый и запрещённый `user_id`
- [x] Слои `bot` / `graph` / `services` / `repositories` заведены как пакеты, зависимости направлены строго внутрь

## Comments

Implemented in `6822691`.

- `.env` is not read by the application; use `uv run --env-file .env python -m bot` locally and
  a systemd `EnvironmentFile` on the VPS. Keeps the dependency list free of `python-dotenv`.
- The whitelist is a root filter on the dispatcher (`dispatcher.message.filter`), which aiogram
  checks before any router or handler filter — strangers never reach a handler.
