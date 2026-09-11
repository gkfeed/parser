from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.item_hash import ItemHash
from app.serializers.feed import Item
from app.services.container import Container
from app.services.repositories.item import ItemsRepository


def make_item(hash: str, suffix: str = "") -> Item:
    return Item(
        title=f"Item {suffix}",
        text="text",
        date=datetime.now(UTC),
        link=f"https://test.com/item/{suffix}",
        hash=hash,
    )


@pytest.mark.asyncio
async def test_seen_hash_is_not_saved_again(create_feed):
    feed = await create_feed()
    hash_val = f"hash-{datetime.now(UTC).timestamp()}"

    first_result = await ItemsRepository.add_items_to_feed(
        feed, [make_item(hash_val, "first")]
    )
    second_result = await ItemsRepository.add_items_to_feed(
        feed, [make_item(hash_val, "second")]
    )

    assert len(first_result) == 1
    assert second_result == []
    assert len(await ItemsRepository.get_all(feed)) == 1


@pytest.mark.asyncio
async def test_hashes_are_scoped_by_feed(create_feed):
    feed1 = await create_feed("Feed 1")
    feed2 = await create_feed("Feed 2")
    hash_val = f"scoped-hash-{datetime.now(UTC).timestamp()}"

    first_result = await ItemsRepository.add_items_to_feed(
        feed1, [make_item(hash_val, "first")]
    )
    second_result = await ItemsRepository.add_items_to_feed(
        feed2, [make_item(hash_val, "second")]
    )

    assert len(first_result) == 1
    assert len(second_result) == 1


@pytest.mark.asyncio
async def test_legacy_hash_is_claimed_by_first_feed(create_feed):
    feed1 = await create_feed("Claim Feed 1")
    feed2 = await create_feed("Claim Feed 2")
    hash_val = f"global-hash-{datetime.now(UTC).timestamp()}"

    async with Container.get_data().db_session() as session, session.begin():
        session.add(ItemHash(hash=hash_val, feed_id=None))

    first_result = await ItemsRepository.add_items_to_feed(
        feed1, [make_item(hash_val, "first")]
    )
    second_result = await ItemsRepository.add_items_to_feed(
        feed2, [make_item(hash_val, "second")]
    )

    assert first_result == []
    assert len(second_result) == 1

    async with Container.get_data().db_session() as session:
        result = await session.execute(
            select(ItemHash).where(ItemHash.hash == hash_val)
        )
        feed_ids = {item.feed_id for item in result.scalars().all()}

    assert feed_ids == {feed1.id, feed2.id}
