import asyncio
import signal
from threading import Event

import structlog

from app.configs.env import SELENIUM_DOCKER_URL
from app.configs.workers import browser_parsers
from app.core.worker import run_worker
from app.utils.is_in_docker import IS_IN_DOCKER
from app.utils.logging import configure_logging
from app.utils.selenium import cleanup_grid

logger = structlog.get_logger(__name__)


async def prepare_grid(server_url: str) -> None:
    stop_event = Event()
    try:
        await asyncio.to_thread(cleanup_grid, server_url, stop_event=stop_event)
    finally:
        stop_event.set()


async def main() -> None:
    task = asyncio.current_task()
    assert task is not None

    def stop() -> None:
        if not task.cancelling():
            task.cancel()

    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop)

    if IS_IN_DOCKER:
        await prepare_grid(SELENIUM_DOCKER_URL)

    while True:
        for parser_type in browser_parsers:
            await run_worker(parser_type)


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("worker_failed", worker="browser")
        raise SystemExit(1)
