# NOTE: generated
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from app.core.dispatcher import Dispatcher
from app.serializers.feed import Feed, Item
from app.services.broker import BrokerError


@pytest.fixture
def dispatcher():
    class FakeFeedParserRepository:
        get_by_feed_id = AsyncMock(return_value=None)
        upsert = AsyncMock()

    class FakeItemHashRepository:
        contains = AsyncMock(return_value=False)
        save = AsyncMock()

    return Dispatcher(
        broker=AsyncMock(),
        feed_parser_repository=FakeFeedParserRepository,
        item_hash_repository=FakeItemHashRepository,
        parsers={},
    )


@pytest.mark.asyncio
async def test_should_process_feed_no_parser(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")
    dispatcher.feed_parser_repository.get_by_feed_id.return_value = None

    assert await dispatcher._should_process_feed(feed) is True
    dispatcher.feed_parser_repository.get_by_feed_id.assert_awaited_once_with(feed.id)


@pytest.mark.asyncio
async def test_should_process_feed_valid_in_past(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")
    mock_feed_parser = MagicMock()
    mock_feed_parser.valid_for = datetime.now(timezone.utc) - timedelta(minutes=1)
    dispatcher.feed_parser_repository.get_by_feed_id.return_value = mock_feed_parser

    assert await dispatcher._should_process_feed(feed) is True


@pytest.mark.asyncio
async def test_should_process_feed_naive_datetime(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")
    mock_feed_parser = MagicMock()
    # Naive datetime (past) based on UTC
    mock_feed_parser.valid_for = datetime.now(timezone.utc).replace(
        tzinfo=None
    ) - timedelta(minutes=10)
    dispatcher.feed_parser_repository.get_by_feed_id.return_value = mock_feed_parser

    assert await dispatcher._should_process_feed(feed) is True


@pytest.mark.asyncio
async def test_should_process_feed_valid_in_future(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")
    mock_feed_parser = MagicMock()
    mock_feed_parser.valid_for = datetime.now(timezone.utc) + timedelta(minutes=1)
    dispatcher.feed_parser_repository.get_by_feed_id.return_value = mock_feed_parser

    assert await dispatcher._should_process_feed(feed) is False


@pytest.mark.asyncio
async def test_filter_seen_items(dispatcher):
    items = [
        Item(
            title="Item 1",
            text="Text 1",
            date=datetime.now(),
            link="http://item1.com",
            hash="hash1",
        ),
        Item(
            title="Item 2",
            text="Text 2",
            date=datetime.now(),
            link="http://item2.com",
            hash="hash2",
        ),
        Item(
            title="Item 3",
            text="Text 3",
            date=datetime.now(),
            link="http://item3.com",
            hash=None,
        ),
    ]
    dispatcher.item_hash_repository.contains.side_effect = lambda h, f: h == "hash1"

    filtered = await dispatcher._filter_seen_items(feed_id=1, items=items)

    assert len(filtered) == 2
    assert filtered[0].title == "Item 2"
    assert filtered[1].title == "Item 3"
    dispatcher.item_hash_repository.save.assert_called_once_with("hash2", 1)


@pytest.mark.asyncio
async def test_request_items_from_broker_success(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")
    items = [
        Item(
            title="Item 1",
            text="Text 1",
            date=datetime.now(timezone.utc),
            link="http://item1.com",
            hash="hash1",
        ),
    ]
    items_json = f"[{items[0].model_dump_json()}]"

    dispatcher.broker.put_and_wait_for_result.return_value = items_json

    result = await dispatcher._request_items_from_broker(feed)

    assert len(result) == 1
    assert result[0].title == "Item 1"
    dispatcher.broker.put_and_wait_for_result.assert_called_once()


@pytest.mark.asyncio
async def test_request_items_from_broker_error(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")

    dispatcher.broker.put_and_wait_for_result.side_effect = BrokerError("Error")

    result = await dispatcher._request_items_from_broker(feed)

    assert result == []


@pytest.mark.asyncio
async def test_fetch_feed_items_no_parser(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="unknown")

    with patch.object(
        dispatcher, "_request_items_from_broker", new_callable=AsyncMock
    ) as mock_request:
        await dispatcher._fetch_feed_items(feed)
        mock_request.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_feed_items_success(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")
    items = [
        Item(
            title="Item 1",
            text="Text 1",
            date=datetime.now(timezone.utc),
            link="http://item1.com",
        )
    ]

    class MockParser:
        _cache_storage_time_if_success = timedelta(hours=2)

    dispatcher.parsers = {"test": MockParser}

    with (
        patch.object(
            dispatcher, "_request_items_from_broker", new_callable=AsyncMock
        ) as mock_request,
        patch.object(
            dispatcher, "_filter_seen_items", new_callable=AsyncMock
        ) as mock_filter,
        patch.object(dispatcher, "_save_items", new_callable=AsyncMock) as mock_save,
    ):
        mock_request.return_value = items
        mock_filter.return_value = items

        await dispatcher._fetch_feed_items(feed)

        mock_filter.assert_awaited_once_with(feed.id, items)
        mock_save.assert_called_once_with(feed, items)
        dispatcher.feed_parser_repository.upsert.assert_called_once()
        # Verify that the expiration date is roughly current time + 2 hours
        call_args = dispatcher.feed_parser_repository.upsert.call_args[0]
        assert call_args[0] == feed.id
        assert (
            abs(
                (
                    call_args[1] - (datetime.now(timezone.utc) + timedelta(hours=2))
                ).total_seconds()
            )
            < 10
        )


@pytest.mark.asyncio
async def test_fetch_feed_items_no_items(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")

    class MockParser:
        _cache_storage_time = timedelta(minutes=30)

    dispatcher.parsers = {"test": MockParser}

    with (
        patch.object(
            dispatcher, "_request_items_from_broker", new_callable=AsyncMock
        ) as mock_request,
        patch.object(dispatcher, "_save_items", new_callable=AsyncMock) as mock_save,
    ):
        mock_request.return_value = []

        await dispatcher._fetch_feed_items(feed)

        mock_save.assert_not_called()
        dispatcher.feed_parser_repository.upsert.assert_called_once()
        # Verify that the expiration date is roughly current time + 30 minutes
        call_args = dispatcher.feed_parser_repository.upsert.call_args[0]
        assert call_args[0] == feed.id
        assert (
            abs(
                (
                    call_args[1] - (datetime.now(timezone.utc) + timedelta(minutes=30))
                ).total_seconds()
            )
            < 10
        )


@pytest.mark.asyncio
async def test_dispatch(dispatcher):
    feeds = [
        Feed(id=1, title="Feed 1", url="http://feed1.com", type="type1"),
        Feed(id=2, title="Feed 2", url="http://feed2.com", type="type2"),
    ]

    with (
        patch.object(
            dispatcher, "_get_all_feeds", new_callable=AsyncMock
        ) as mock_get_feeds,
        patch.object(
            dispatcher, "_should_process_feed", new_callable=AsyncMock
        ) as mock_should_process,
        patch.object(
            dispatcher, "_fetch_feed_items", new_callable=AsyncMock
        ) as mock_fetch,
    ):
        mock_get_feeds.return_value = feeds
        mock_should_process.side_effect = lambda f: f.id == 1

        await dispatcher.dispatch()

        assert mock_fetch.call_count == 1
        mock_fetch.assert_called_once_with(feeds[0])
