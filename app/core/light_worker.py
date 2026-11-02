import asyncio
import math
from collections.abc import Sequence
from itertools import cycle

import structlog

from app.configs.env import BROKER_URL
from app.core.parser_id import ParserId
from app.core.worker import run_task
from app.services.broker import BrokerService

logger = structlog.get_logger(__name__)


async def run_light_workers(
    parser_ids: Sequence[ParserId],
    *,
    idle_poll_min: float = 0.1,
    idle_poll_max: float = 1.0,
    broker: BrokerService | None = None,
) -> None:
    """Process one feed at a time; scale concurrency with worker containers.

    Cancellation stops new claims and drains the current claim, parsing, and
    terminal broker submission before returning to the process lifecycle.
    """
    if not parser_ids:
        raise ValueError("At least one light parser is required")
    if not 0 < idle_poll_min <= idle_poll_max or not math.isfinite(idle_poll_max):
        raise ValueError("Idle polling delays must be finite, positive and ordered")

    queues = tuple(dict.fromkeys(ParserId(parser_id) for parser_id in parser_ids))
    broker = broker if broker is not None else BrokerService(BROKER_URL)
    empty_polls = 0
    delay = idle_poll_min
    for parser_id in cycle(queues):
        if await _run_job(parser_id, broker):
            empty_polls = 0
            delay = idle_poll_min
            continue
        empty_polls += 1
        if empty_polls < len(queues):
            continue
        await asyncio.sleep(delay)
        empty_polls = 0
        delay = min(delay * 2, idle_poll_max)


async def _run_job(parser_id: ParserId, broker: BrokerService) -> bool:
    # Shield the whole claim-to-submission operation: a claim may have reached
    # the broker even when its HTTP response has not reached the worker yet.
    job = asyncio.create_task(_claim_and_process(parser_id, broker))
    try:
        return await asyncio.shield(job)
    except asyncio.CancelledError:
        logger.info("light_worker_draining", jobs=1)
        try:
            await job
        except Exception:
            logger.exception("light_worker_drain_failed")
        raise


async def _claim_and_process(parser_id: ParserId, broker: BrokerService) -> bool:
    task = await broker.get_task(parser_id.task_name)
    if task is None:
        return False
    await run_task(task, parser_id, broker)
    return True
