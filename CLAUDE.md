# TimeKnot

## Project status

**Tickets 01–05 done** — skeleton, config, whitelist, `/start`, SQLite storage, `/tasks`, the
`handle_message` seam over a LangGraph state graph, live extraction through OpenRouter with real
task creation, and the `dispatch_due` seam firing reminders through APScheduler. 61 tests green.
Next unblocked tickets: `06` (restart recovery), `07` (reminder buttons), `10` (parsing
resilience).

`list_tasks`, `complete_task` and `smalltalk` are still stub nodes (`[stub …]` replies) —
ticket 09 fills them in. Running the bot now needs `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`.
Tests never touch the network: they drive `handle_message` with `ScriptedLLMClient`.

The product is a single-user Russian-language Telegram task/reminder assistant. The spec and a
12-ticket breakdown live at `.scratch/telegram-task-assistant/`; read `spec.md` before writing
code. Everything below the "Tech stack" heading that is not yet backed by code (OpenRouter,
`AsyncSqliteSaver`, APScheduler, Jupytext) is still the *intended* setup — update it as tickets
land.

Run locally: `uv run --env-file .env python -m bot` (see `.env.example`).

## Tech stack

- **Language**: Python 3.11+ (managed exclusively with `uv`)
- **Telegram**: aiogram 3.x, long polling
- **Dialog orchestration**: LangGraph state graph; conversation state in `AsyncSqliteSaver`
- **LLM**: OpenRouter (OpenAI-compatible client), model id from env. Structured output is
  validated with Pydantic v2 and retried once — strict JSON-schema mode is not assumed
- **Scheduling**: APScheduler `AsyncIOScheduler` with `MemoryJobStore`. The `tasks` table is the
  single source of truth; the scheduler is only a timer cache, rehydrated on startup
- **Database**: SQLite via `aiosqlite`, SQLAlchemy 2 async, Repository Pattern. All timestamps
  stored in UTC; local time exists only at the boundaries
- **Notebooks**: Jupyter notebooks paired to `.py` percent-format scripts via Jupytext
- **Lint / format**: Ruff
- **Tests**: Pytest

## Project structure

```
/
├── CLAUDE.md              # This file
├── CONTEXT.md             # Domain glossary (created lazily by /domain-modeling)
├── docs/
│   ├── adr/               # Architecture Decision Records
│   └── agents/            # Agent workflow config (see "Agent skills")
├── .scratch/              # Issue tracker: one dir per feature
│   └── telegram-task-assistant/   # spec.md + issues/01..12
└── src/                   # Application code (not created yet)
    ├── bot/               # aiogram handlers, keyboards, DI
    ├── graph/             # LangGraph nodes, state, Pydantic schemas
    ├── services/          # use cases
    ├── repositories/      # SQLAlchemy 2 async
    └── scheduler/         # APScheduler, rehydration, catch-up
```

Dependencies point strictly inward: `bot` → `graph` → `services` → `repositories`.
Only three boundaries are faked in tests — the LLM client, the Telegram sender, and the clock.
Everything else, including SQLite, is real.

## Setup

```bash
uv sync                    # Create/refresh the virtualenv from the lockfile
uv run pytest              # Run the test suite
uv run ruff check --fix .  # Lint with autofix
uv run ruff format .       # Format
```

## Environment, quality & testing

- **ALWAYS** use `uv` for environment management, package installation, and running scripts
  (`uv sync`, `uv add <pkg>`, `uv run <cmd>`). Never call `pip`, `python -m venv`, or a bare `python`.
- **ALWAYS** run `ruff check --fix . && ruff format .` after modifying any Python code.
- If tests exist, **ALWAYS** run them (`uv run pytest`) after making changes, and report the result.

## CLI restrictions & tools

- **STRICTLY FORBIDDEN** to read or edit `.ipynb` files directly. Always work with the paired
  `.py` file (Jupytext percent script format). After editing the `.py`, run `jupytext --sync <file>.py`
  to propagate the change to the notebook.
- Use **`sg` (ast-grep)** for structural Python search and refactoring instead of `grep`/`sed`.
  Example: `sg --lang python -p 'def $NAME($$$)'`. Plain text search is fine for non-code files.

## MCP priority policy (routing)

1. **Orientation and code relationships → `codebase-memory-mcp` FIRST.**
   Use `get_architecture` for structure and `trace_path` for call chains / data flow before
   editing architecture or hunting for relationships. Do not read files manually just to orient.
   If the project is not indexed yet, run `index_repository` first.
2. **Complex multi-step refactoring or bug hunting → ALWAYS trigger Sequential Thinking MCP**
   (`sequentialthinking`) before making changes.
3. **Uncertain about a library API → fetch current docs via Fetch MCP.** Do not answer from memory.

## Behavioral rules (every session)

- **User language**: ALWAYS respond to the user in **Russian**. Internal reasoning, tool calls,
  code, commit messages, and this file stay in English.
- **Caveman mode**: extremely concise, direct, zero fluff. No pleasantries, no preambles,
  no long explanations, no restating the question.
- **Karpathy mode**: minimal diffs. Do not refactor, reformat, or "improve" code unrelated
  to the change requested.
- **Git commits**: never add a `Co-authored-by` trailer and never add
  "Generated with Claude Code" or any similar attribution to commits, PRs, or commands.
- **Long tasks**: do not execute heavy scripts, training runs, or large downloads automatically
  in Bash. Print the command and let the user run it.
- **Error safety**: if a command or test fails, DO NOT retry it blindly. Analyze the root cause,
  state it, then act.

## Agent skills

### Issue tracker

Issues and specs live as markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary, label string equals role name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Maintaining this file

Keep it under 150 lines. If it grows past that, move detail into sub-files and reference them
with `@path` imports (e.g. `@docs/agents/domain.md`).
