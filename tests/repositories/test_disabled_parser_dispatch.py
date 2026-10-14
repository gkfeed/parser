from datetime import UTC, datetime, timedelta

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.core.dispatcher import Dispatcher
from app.serializers.feed import Feed, FeedResult, Item
from app.services.broker import BrokerService
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository


@pytest.mark.integration
async def test_disabled_feeds_are_preserved_without_scheduling():
    disabled = await FeedRepository.create(
        Feed(
            id=0,
            title="Closed channel",
            type="matreshka",
            url="https://matreshka.tv/channel/HgIgri0SAvQ/internal/videos",
        )
    )
    active = await FeedRepository.create(
        Feed(id=0, title="Active feed", type="web", url="https://example.com/feed")
    )
    past = datetime.now(UTC) - timedelta(days=1)
    await FeedParserRepository.upsert(disabled.id, past)
    item = Item(
        title="Saved video",
        text="Saved video",
        date=past,
        link="https://matreshka.tv/video/saved",
        hash="saved-video-hash",
    )
    await ItemsRepository.add_items_to_feed(disabled, [item])
    submitted = []

    async def enqueue(request):
        payload = await request.json()
        feed = Feed.model_validate_json(payload["data"][0])
        submitted.append(feed)
        return web.json_response({"task_id": str(feed.id)})

    async def result(request):
        return web.json_response(
            {"status": "completed", "result": FeedResult(items=[]).model_dump_json()}
        )

    app = web.Application()
    app.router.add_post("/enqueue", enqueue)
    app.router.add_get("/result/{task_id}", result)
    async with TestServer(app) as server:
        dispatcher = Dispatcher(broker=BrokerService(str(server.make_url("/"))))
        await dispatcher.dispatch()
        await dispatcher.dispatch()

    assert submitted == [active]
    assert await FeedRepository.get_by_id(disabled.id) == disabled
    assert len(await ItemsRepository.get_all(disabled)) == 1
    assert await ItemsRepository.add_items_to_feed(disabled, [item]) == []
    schedule = await FeedParserRepository.get_by_feed_id(disabled.id)
    assert schedule is not None
    assert schedule.valid_for.replace(tzinfo=UTC) == past
