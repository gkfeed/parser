import asyncio
import json
from datetime import UTC, datetime

from app.configs.env import BROKER_URL
from app.extensions.parsers.hash import ItemsHashExtension
from app.parsers import PARSERS
from app.serializers.feed import Feed
from app.services.broker import BrokerService
from app.services.http import HttpClient


async def run_worker(type: str, broker: BrokerService, http: HttpClient) -> None:
    await asyncio.sleep(1)

    task = await broker.get_task(f"gkfeed.process_feed_{type}")

    if not task:
        return

    feed = Feed.model_validate_json(task.args[0])
    parser = PARSERS.get(feed.type)
    print(f"{datetime.now(UTC).strftime('%H:%M')} {type}: {feed.url}")

    if not parser:
        raise ValueError(f"No parser found for feed type: {feed.type}")

    try:
        parser_instance = parser(feed, {}, http=http)
        items = await parser_instance.items

        if isinstance(parser_instance, ItemsHashExtension):
            items = await parser_instance.apply_hashes(items)
    except Exception as e:  # noqa: BLE001 - isolate failures from individual feed parsers
        print(f"Error processing {type}: {e}")
        await broker.submit_error(task.id, "failed")
        return

    print(f"{type}: {len(items)} items found")
    items_json = json.dumps(
        [i.model_dump() for i in items],
        default=lambda o: o.isoformat() if isinstance(o, datetime) else None,
    )

    await broker.submit_result(task.id, items_json)


async def run_workers(parser_types: list[str]) -> None:
    async with HttpClient() as http:
        broker = BrokerService(BROKER_URL, http)
        while True:
            for parser_type in parser_types:
                await run_worker(parser_type, broker, http)
