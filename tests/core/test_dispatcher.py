# NOTE: generated
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.core.dispatcher import Dispatcher
from app.serializers.feed import Feed, Item
from app.services.broker import BrokerError


@pytest.fixture
def dispatcher():
    class FakeFeedParserRepository:
        upsert = AsyncMock()

    return Dispatcher(
        broker=AsyncMock(),
        feed_parser_repository=FakeFeedParserRepository,
        parsers={},
    )


@pytest.mark.asyncio
async def test_request_items_from_broker_success(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")
    items = [
        Item(
            title="Item 1",
            text="Text 1",
            date=datetime.now(UTC),
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

    with pytest.raises(BrokerError):
        await dispatcher._request_items_from_broker(feed)


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
            date=datetime.now(UTC),
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
        patch.object(dispatcher, "_save_items", new_callable=AsyncMock) as mock_save,
    ):
        mock_request.return_value = items
        mock_save.return_value = items

        await dispatcher._fetch_feed_items(feed)

        mock_save.assert_called_once_with(feed, items)
        dispatcher.feed_parser_repository.upsert.assert_called_once()
        # Verify that the expiration date is roughly current time + 2 hours
        call_args = dispatcher.feed_parser_repository.upsert.call_args[0]
        assert call_args[0] == feed.id
        assert (
            abs(
                (
                    call_args[1] - (datetime.now(UTC) + timedelta(hours=2))
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
                    call_args[1] - (datetime.now(UTC) + timedelta(minutes=30))
                ).total_seconds()
            )
            < 10
        )


@pytest.mark.asyncio
async def test_fetch_feed_items_backs_off_after_failures(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")
    dispatcher.parsers = {"test": object}
    dispatcher.broker.put_and_wait_for_result.side_effect = BrokerError("Error")

    with patch("app.core.dispatcher.random.uniform", return_value=1):
        for expected_delay in (
            timedelta(minutes=15),
            timedelta(hours=1),
            timedelta(hours=6),
            timedelta(hours=24),
            timedelta(hours=24),
        ):
            before = datetime.now(UTC)
            await dispatcher._fetch_feed_items(feed)
            after = datetime.now(UTC)

            call_args = dispatcher.feed_parser_repository.upsert.call_args[0]
            assert call_args[0] == feed.id
            assert before + expected_delay <= call_args[1] <= after + expected_delay
            dispatcher.feed_parser_repository.upsert.reset_mock()


@pytest.mark.asyncio
async def test_success_resets_failure_backoff(dispatcher):
    feed = Feed(id=1, title="Test", url="http://test.com", type="test")
    dispatcher.parsers = {"test": object}

    with (
        patch.object(
            dispatcher,
            "_request_items_from_broker",
            new_callable=AsyncMock,
            side_effect=[BrokerError("Error"), [], BrokerError("Error")],
        ),
        patch("app.core.dispatcher.random.uniform", return_value=1),
    ):
        await dispatcher._fetch_feed_items(feed)
        await dispatcher._fetch_feed_items(feed)
        before = datetime.now(UTC)
        await dispatcher._fetch_feed_items(feed)
        after = datetime.now(UTC)

    retry_at = dispatcher.feed_parser_repository.upsert.call_args[0][1]
    expected_delay = timedelta(minutes=15)
    assert before + expected_delay <= retry_at <= after + expected_delay
