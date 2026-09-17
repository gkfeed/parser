import asyncio
import json
import logging
from datetime import datetime
from time import monotonic

from app.configs.env import BROKER_URL
from app.extensions.parsers.hash import ItemsHashExtension
from app.parsers import PARSERS
from app.serializers.feed import Feed
from app.services.broker import BrokerService, Task
from app.utils.logging import log_context

logger = logging.getLogger(__name__)


async def run_worker(type: str):
    await asyncio.sleep(1)

    broker = BrokerService(BROKER_URL)
    task = await broker.get_task(f"gkfeed.process_feed_{type}")

    if not task:
        return

    with log_context(task_id=task.id, parser=type):
        feed = Feed.model_validate_json(task.args[0])
        with log_context(feed_id=feed.id):
            await _process_feed(task, feed, broker)


async def _process_feed(task: Task, feed: Feed, broker: BrokerService) -> None:
    started = monotonic()
    parser = PARSERS.get(feed.type)
    logger.info("Feed processing started")

    if not parser:
        raise ValueError(f"No parser found for feed type: {feed.type}")

    try:
        parser_instance = parser(feed, {})
        items = await parser_instance.items

        if isinstance(parser_instance, ItemsHashExtension):
            items = await parser_instance.apply_hashes(items)
    except Exception:
        logger.exception(
            "Feed processing failed duration_seconds=%.3f", monotonic() - started
        )
        await broker.submit_error(task.id, "failed")
        return

    logger.info(
        "Feed parsed items=%d duration_seconds=%.3f", len(items), monotonic() - started
    )
    items_json = json.dumps(
        [i.model_dump() for i in items],
        default=lambda o: o.isoformat() if isinstance(o, datetime) else None,
    )

    await broker.submit_result(task.id, items_json)
    logger.info("Feed result submitted items=%d", len(items))
