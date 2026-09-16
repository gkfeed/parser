from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.models.feed_parser import FeedParser
from app.models.item import Item as ItemModel
from app.models.item_hash import ItemHash
from app.serializers.feed import Item
from app.services.container import Container
from app.services.repositories.feed import FeedRepository
from app.services.repositories.feed_parser import FeedParserRepository
from app.services.repositories.item import ItemsRepository


@pytest.mark.asyncio
async def test_deleting_feed_cascades_to_dependents(create_feed):
    feed = await create_feed("Cascade feed")

    item = Item(
        title="Cascade item",
        text="text",
        date=datetime.now(UTC),
        link=f"https://cascade.test/{datetime.now(UTC).timestamp()}",
        hash="cascade-hash",
    )
    await ItemsRepository.add_items_to_feed(feed, [item])
    await FeedParserRepository.upsert(feed.id, datetime.now(UTC))

    async with Container.get_data().db_session() as session:
        item_count = await session.scalar(
            select(func.count()).select_from(ItemModel).where(ItemModel.feed_id == feed.id)
        )
        hash_count = await session.scalar(
            select(func.count()).select_from(ItemHash).where(ItemHash.feed_id == feed.id)
        )
        parser_count = await session.scalar(
            select(func.count()).select_from(FeedParser).where(FeedParser.feed_id == feed.id)
        )
    assert (item_count, hash_count, parser_count) == (1, 1, 1)

    await FeedRepository.delete_by_id(feed.id)

    async with Container.get_data().db_session() as session:
        remaining_items = await session.scalar(
            select(func.count()).select_from(ItemModel).where(ItemModel.feed_id == feed.id)
        )
        remaining_hashes = await session.scalar(
            select(func.count()).select_from(ItemHash).where(ItemHash.feed_id == feed.id)
        )
        remaining_parser_state = await session.scalar(
            select(func.count()).select_from(FeedParser).where(FeedParser.feed_id == feed.id)
        )
    assert (remaining_items, remaining_hashes, remaining_parser_state) == (0, 0, 0)
    with pytest.raises(ValueError):
        await FeedRepository.get_by_id(feed.id)


@pytest.mark.asyncio
async def test_unique_feed_hash_constraint(create_feed):
    feed = await create_feed("Unique hash feed")
    item = Item(
        title="Unique item",
        text="text",
        date=datetime.now(UTC),
        link=f"https://unique.test/{datetime.now(UTC).timestamp()}",
        hash="unique-feed-hash",
    )
    await ItemsRepository.add_items_to_feed(feed, [item])
    await ItemsRepository.add_items_to_feed(
        feed,
        [
            Item(
                title="Different item same hash",
                text="text",
                date=datetime.now(UTC),
                link=f"https://unique.test/other/{datetime.now(UTC).timestamp()}",
                hash="unique-feed-hash",
            )
        ],
    )

    async with Container.get_data().db_session() as session:
        hash_rows = await session.scalars(
            select(ItemHash).where(ItemHash.hash == "unique-feed-hash")
        )
    assert len(hash_rows.all()) == 1
