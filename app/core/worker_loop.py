import asyncio
import signal
from collections.abc import Sequence
from threading import Event

import structlog

from app.configs.env import SELENIUM_DOCKER_URL
from app.core.light_worker import run_light_workers
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
        raise ValueError("A worker cannot mix light and heavy parsers")
    return kinds.pop()


async def _run_sequential_workers(parser_ids: Sequence[ParserId]) -> None:
    while True:
        for parser_id in parser_ids:
            await run_worker(parser_id)


async def run_workers(parser_ids: Sequence[ParserId]) -> None:
    """Run one worker process with the scheduling policy of its parsers."""
    parser_ids = tuple(parser_ids)
    kind = _worker_kind(parser_ids)
    task = asyncio.current_task()
    assert task is not None

    def stop() -> None:
        # Further signals must not interrupt scheduler draining or parser cleanup.
        if not task.cancelling():
            task.cancel()

    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop)

    try:
        await _run_workers(parser_ids, kind)
    finally:
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)


async def _run_workers(parser_ids: Sequence[ParserId], kind: WorkerKind) -> None:
    if kind == WorkerKind.LIGHT:
        await run_light_workers(parser_ids)
        return
    if IS_IN_DOCKER:
        await _prepare_grid(SELENIUM_DOCKER_URL)
    await _run_sequential_workers(parser_ids)


def main(parser_ids: Sequence[ParserId]) -> None:
    configure_logging()
    kind = _worker_kind(parser_ids)
    try:
        asyncio.run(run_workers(parser_ids))
    except asyncio.CancelledError:
        pass
    except Exception:
        if kind != WorkerKind.HEAVY:
            raise
        logger.exception("worker_failed", worker=kind)
        raise SystemExit(1)
