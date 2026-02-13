import asyncio
import json
from datetime import datetime

from app.parsers import PARSERS
from app.configs.env import BROKER_URL
from app.serializers.feed import Feed
from app.services.broker import BrokerService


async def run_worker(type: str):
    await asyncio.sleep(1)

    broker = BrokerService(BROKER_URL)
    task = await broker.get_task(f"gkfeed.process_feed_{type}")

    if not task:
        return

    feed = Feed.model_validate_json(task.args[0])
    parser = PARSERS.get(feed.type)
    print(f"{type}: {feed.url}")

    if not parser:
        raise ValueError(f"No parser found for feed type: {feed.type}")

    try:
        items = await parser(feed, {}).items
    except Exception as e:
        print(f"Error processing {type}: {e}")
        await BrokerService(BROKER_URL).submit_error(task.id, "failed")
        return

    items_json = json.dumps(
        [i.model_dump() for i in items],
        default=lambda o: o.isoformat() if isinstance(o, datetime) else None,
    )

    await BrokerService(BROKER_URL).submit_result(task.id, items_json)
