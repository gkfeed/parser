import asyncio
import signal
from collections.abc import Sequence
from itertools import cycle
from threading import Event

import structlog

from app.configs.env import SELENIUM_DOCKER_URL
from app.core.parser_id import ParserId
from app.core.worker import run_worker
from app.core.worker_kind import WorkerKind
from app.parsers import PARSERS
from app.utils.is_in_docker import IS_IN_DOCKER
from app.utils.logging import configure_logging
from app.utils.selenium import cleanup_grid

logger = structlog.get_logger(__name__)


async def _prepare_grid(server_url: str) -> None:
    stop_event = Event()
    try:
        await asyncio.to_thread(cleanup_grid, server_url, stop_event=stop_event)
    finally:
        stop_event.set()


def _worker_kind(parser_ids: Sequence[ParserId]) -> WorkerKind:
    if not parser_ids:
        raise ValueError("A worker requires at least one parser")
    kinds = {PARSERS[parser_id].worker_kind for parser_id in parser_ids}
    if len(kinds) != 1:
        raise ValueError("A worker cannot mix parser worker kinds")
    return kinds.pop()


async def _run_sequential_workers(
    parser_ids: Sequence[ParserId], stop_event: asyncio.Event
) -> None:
    for parser_id in cycle(parser_ids):
        if stop_event.is_set():
            return
        await run_worker(parser_id)


async def _run_workers(parser_ids: Sequence[ParserId], kind: WorkerKind) -> None:
    """Run assigned queues sequentially in one process event loop."""
    task = asyncio.current_task()
    assert task is not None
    stop_event = asyncio.Event()

    def stop() -> None:
        stop_event.set()
        # Browser cancellation preserves Selenium cleanup. Other workers finish
        # their current broker operation before the sequential loop exits.
        if kind == WorkerKind.BROWSER and not task.cancelling():
            task.cancel()

    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop)

    try:
        if kind == WorkerKind.BROWSER and IS_IN_DOCKER:
            await _prepare_grid(SELENIUM_DOCKER_URL)
        await _run_sequential_workers(parser_ids, stop_event)
    finally:
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)


def main(parser_ids: Sequence[ParserId]) -> None:
    configure_logging()
    parser_ids = tuple(parser_ids)
    kind = _worker_kind(parser_ids)
    try:
        asyncio.run(_run_workers(parser_ids, kind))
    except asyncio.CancelledError:
        pass
    except Exception:
        if kind != WorkerKind.BROWSER:
            raise
        logger.exception("worker_failed", worker=kind)
        raise SystemExit(1)
