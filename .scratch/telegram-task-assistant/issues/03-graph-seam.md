# 03 — Граф и шов `handle_message` на фейковом LLM

**What to build:** Появляется главный шов приложения: функция принимает текст, идентификатор пользователя и текущий момент, возвращает ответ бота. Граф LangGraph собран и ветвится по интенту, но за модель отвечает подставной клиент — живой провайдер здесь не нужен.

Это фундамент для всех последующих тикетов: дальше они пишутся и тестируются, не касаясь сети.

**Blocked by:** 02 — Хранилище задач и пустой `/tasks`.

**Status:** done

- [x] Pydantic-схема результата разбора содержит `intent` (`create_task` / `list_tasks` / `complete_task` / `smalltalk`) и поля задачи
- [x] LLM-клиент описан протоколом; реализация в этом тикете — фейк со сценарными ответами
- [x] Часы описаны протоколом; ни один тест не зависит от реального времени
- [x] Граф LangGraph: узел разбора, conditional edge по `intent`, узлы-заглушки для каждой ветки
- [x] Поля задачи читаются только при `intent = create_task` и игнорируются при остальных, даже если заполнены
- [x] Шов `handle_message` вызывается из aiogram-хендлера и покрыт тестами на все четыре ветки
- [x] Тест проверяет ответ бота и содержимое БД, а не имена узлов графа и порядок вызовов репозиториев

## Comments

Implemented in `9319862`.

- Task fields are cleared by a Pydantic `model_validator` when the intent is not `create_task`,
  so no downstream node can read invented values.
- A fifth branch, `unparsed`, was added beyond the ticket: malformed model output and provider
  failures would otherwise raise out of the aiogram handler and the user would get nothing.
  The single parse retry itself still belongs to ticket 04.
- Free text is matched with `F.text & ~F.text.startswith("/")` rather than relying on the
  handler being registered after the commands.
- LangGraph requires the node parameter to be named exactly `state`.
