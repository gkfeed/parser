import asyncio
import math
from collections.abc import Sequence
from itertools import cycle

import structlog

from app.configs.env import BROKER_URL, LIGHT_WORKER_CONCURRENCY
from app.core.parser_id import ParserId
from app.core.worker import run_task
from app.services.broker import BrokerService

logger = structlog.get_logger(__name__)


async def run_light_workers(
    parser_ids: Sequence[ParserId],
    *,
    concurrency: int = LIGHT_WORKER_CONCURRENCY,
    idle_poll_min: float = 0.1,
    idle_poll_max: float = 1.0,
    broker: BrokerService | None = None,
) -> None:
    """Poll queues fairly and drain accepted jobs when the runner is cancelled.

    Slots include parsing and terminal broker submissions. Even an in-progress
    claim is allowed to finish during shutdown, since it may already have been
    accepted by the broker. No new claims start after cancellation.
    """
    if not parser_ids:
        raise ValueError("At least one light parser is required")
    if concurrency < 1:
        raise ValueError("concurrency must be greater than zero")
    if not 0 < idle_poll_min <= idle_poll_max or not math.isfinite(idle_poll_max):
        raise ValueError("Idle polling delays must be finite, positive and ordered")

    jobs: set[asyncio.Task[None]] = set()
    try:
        await _poll_queues(
            tuple(dict.fromkeys(ParserId(parser_id) for parser_id in parser_ids)),
            broker if broker is not None else BrokerService(BROKER_URL),
            jobs,
            concurrency,
            idle_poll_min,
            idle_poll_max,
        )
    except BaseException:
        # Preserve the triggering failure, but wait for every accepted job and
        # make any additional drain failure visible before leaving the loop.
        await _drain_after_failure(jobs)
        raise


async def _poll_queues(
    parser_ids: Sequence[ParserId],
    broker: BrokerService,
    jobs: set[asyncio.Task[None]],
    concurrency: int,
    idle_poll_min: float,
    idle_poll_max: float,
) -> None:
    empty_polls = 0
    delay = idle_poll_min
    for parser_id in cycle(parser_ids):
        _reap_jobs(jobs)
        if len(jobs) >= concurrency:
            await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
            _reap_jobs(jobs)

        if await _claim_job(parser_id, broker, jobs):
            empty_polls = 0
            delay = idle_poll_min
            continue

        empty_polls += 1
        if empty_polls < len(parser_ids):
            continue
        # Sleep only after a complete empty sweep, including when another job
        # is still running. Busy queues never pay this idle delay.
        await asyncio.sleep(delay)
        empty_polls = 0
        delay = min(delay * 2, idle_poll_max)


async def _claim_job(
    parser_id: ParserId, broker: BrokerService, jobs: set[asyncio.Task[None]]
) -> bool:
    claim = asyncio.create_task(_claim_and_start(parser_id, broker, jobs))
    try:
        return await asyncio.shield(claim)
    except asyncio.CancelledError:
        await claim
        raise


async def _claim_and_start(
    parser_id: ParserId, broker: BrokerService, jobs: set[asyncio.Task[None]]
) -> bool:
    task = await broker.get_task(parser_id.task_name)
    if task is None:
        return False
    jobs.add(asyncio.create_task(run_task(task, parser_id, broker)))
    return True


def _reap_jobs(jobs: set[asyncio.Task[None]]) -> None:
    done = {job for job in jobs if job.done()}
    jobs.difference_update(done)
    # Retrieve every outcome even if several jobs failed simultaneously.
    errors = [job.exception() for job in done]
    for error in errors:
        if error is not None:
            raise error


async def _drain_after_failure(jobs: set[asyncio.Task[None]]) -> None:
    if not jobs:
        return
    logger.info("light_worker_draining", jobs=len(jobs))
    results = await asyncio.gather(*jobs, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            logger.error("light_worker_drain_failed", exc_info=result)
