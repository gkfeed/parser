import asyncio
import json
from datetime import datetime
from time import monotonic

import structlog
from structlog.contextvars import bound_contextvars, clear_contextvars

from app.configs.env import BROKER_URL
from app.extensions.parsers.hash import ItemsHashExtension
from app.parsers import PARSERS
from app.serializers.feed import Feed
from app.services.broker import BrokerService, Task

logger = structlog.get_logger(__name__)


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
    except Exception:
        logger.exception(
            "feed_processing_failed", duration_seconds=monotonic() - started
        )
        await broker.submit_error(task.id, "failed")
        return

    logger.info("feed_parsed", items=len(items), duration_seconds=monotonic() - started)
    items_json = json.dumps(
        [i.model_dump() for i in items],
        default=lambda o: o.isoformat() if isinstance(o, datetime) else None,
    )

    await broker.submit_result(task.id, items_json)
    logger.info("feed_result_submitted", items=len(items))
