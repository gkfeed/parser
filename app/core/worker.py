import asyncio
import json
from datetime import datetime
from time import monotonic

import structlog
from structlog.contextvars import bound_contextvars, clear_contextvars

from app.configs.env import BROKER_URL
from app.extensions.parsers.base import BaseFeed
from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.hash import ItemsHashExtension
from app.extensions.parsers.result_size import ResultSizeExtension
from app.parsers import PARSERS
from app.serializers.feed import Feed, FeedFailure, Item
from app.services.broker import BrokerError, BrokerResultTooLarge, BrokerService, Task

logger = structlog.get_logger(__name__)
_MAX_RESULT_RESIZE_ATTEMPTS = 8


async def run_worker(type: str):
    clear_contextvars()
    await asyncio.sleep(1)

    broker = BrokerService(BROKER_URL)
    task = await broker.get_task(f"gkfeed.process_feed_{type}")

    if not task:
        return

    with bound_contextvars(task_id=task.id, parser=type):
        feed = Feed.model_validate_json(task.args[0])
        with bound_contextvars(feed_id=feed.id):
            await _process_feed(task, feed, broker)


async def _process_feed(task: Task, feed: Feed, broker: BrokerService) -> None:
    started = monotonic()
    parser = PARSERS.get(feed.type)
    logger.info("feed_processing_started")

    if not parser:
        raise ValueError(f"No parser found for feed type: {feed.type}")

    try:
        parser_instance = parser(feed, {})
        items = await parser_instance.items

        if isinstance(parser_instance, ItemsHashExtension):
            items = await parser_instance.apply_hashes(items)
    except FeedUnavailable as exc:
        logger.warning(
            "feed_unavailable",
            reason=exc.reason,
            retry_at=exc.retry_at.isoformat() if exc.retry_at else None,
            duration_seconds=monotonic() - started,
        )
        error = FeedFailure(
            error_type="feed_unavailable", reason=exc.reason, retry_at=exc.retry_at
        ).model_dump_json()
        await _submit_error(broker, task.id, error)
        return
    except Exception:
        logger.exception(
            "feed_processing_failed", duration_seconds=monotonic() - started
        )
        await _submit_error(broker, task.id, "failed")
        return

    logger.info("feed_parsed", items=len(items), duration_seconds=monotonic() - started)
    try:
        await _submit_result(broker, task.id, parser_instance, items)
    except Exception:
        logger.exception("feed_result_submission_failed", items=len(items))
        await _submit_error(broker, task.id, "result_submission_failed")
        return
    logger.info("feed_result_submitted", items=len(items))


async def _submit_result(
    broker: BrokerService, task_id: str, parser: BaseFeed, items: list[Item]
) -> None:
    original_items = items
    rejected_size: int | None = None
    for attempt in range(_MAX_RESULT_RESIZE_ATTEMPTS + 1):
        items_json = json.dumps(
            [i.model_dump() for i in items],
            default=lambda o: o.isoformat() if isinstance(o, datetime) else None,
        )
        if rejected_size is not None and len(items_json) >= rejected_size:
            raise BrokerResultTooLarge("Result cannot be reduced further")
        try:
            await broker.submit_result(task_id, items_json)
            return
        except BrokerResultTooLarge:
            if (
                not isinstance(parser, ResultSizeExtension)
                or attempt == _MAX_RESULT_RESIZE_ATTEMPTS
            ):
                raise
            rejected_size = len(items_json)
        smaller_items = await parser.reduce_result_size(original_items, attempt + 1)
        if smaller_items is None:
            raise BrokerResultTooLarge("Result cannot be reduced further")
        items = smaller_items
        logger.info("feed_result_resized", attempt=attempt + 1, items=len(items))


async def _submit_error(broker: BrokerService, task_id: str, error: str) -> None:
    try:
        await broker.submit_error(task_id, error)
    except BrokerError:
        logger.exception("feed_error_submission_failed")
