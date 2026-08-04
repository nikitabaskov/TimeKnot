"""Entry point: `uv run python -m bot`."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys

from bot.app import run_polling
from config import ConfigError, load_config


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    try:
        config = load_config()
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(1) from None

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_polling(config))


if __name__ == "__main__":
    run()
