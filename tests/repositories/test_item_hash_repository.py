import pytest
from datetime import datetime
from sqlalchemy import select
from app.models.item_hash import ItemHash
from app.services.repositories.item_hash import ItemsHashRepository
from app.services.container import Container

@pytest.mark.asyncio
async def test_item_hash_basic_flow(create_feed):
    feed = await create_feed()
    hash_val = f"hash-{datetime.now().timestamp()}"

    # 1. Not contained initially
    assert not await ItemsHashRepository.contains(hash_val, feed.id)

    # 2. Save
    await ItemsHashRepository.save(hash_val, feed.id)

    # 3. Contained
    assert await ItemsHashRepository.contains(hash_val, feed.id)

@pytest.mark.asyncio
async def test_item_hash_scoping(create_feed):
    feed1 = await create_feed("Feed 1")
    feed2 = await create_feed("Feed 2")
    hash_val = f"scoped-hash-{datetime.now().timestamp()}"

    # Save for Feed 1
    await ItemsHashRepository.save(hash_val, feed1.id)
    assert await ItemsHashRepository.contains(hash_val, feed1.id)

    # Check Feed 2 (should be False)
    assert not await ItemsHashRepository.contains(hash_val, feed2.id)

    # Save for Feed 2
    await ItemsHashRepository.save(hash_val, feed2.id)
    assert await ItemsHashRepository.contains(hash_val, feed2.id)

@pytest.mark.asyncio
async def test_item_hash_claim_legacy(create_feed):
    feed1 = await create_feed("Claim Feed 1")
    feed2 = await create_feed("Claim Feed 2")
    hash_val = f"global-hash-{datetime.now().timestamp()}"

    # Manual insert of global hash
    async with Container.get_data().db_session() as session:
        async with session.begin():
            session.add(ItemHash(hash=hash_val, feed_id=None))

    # 1. Feed 1 encounters it -> Claims it
    assert await ItemsHashRepository.contains(hash_val, feed1.id)

    # Verify claim (direct DB check)
    async with Container.get_data().db_session() as session:
        stmt = select(ItemHash).where(ItemHash.hash == hash_val)
        result = await session.execute(stmt)
        item = result.scalars().first()
        assert item.feed_id == feed1.id

    # 2. Feed 2 encounters it -> Should be False (New Item for Feed 2)
    assert not await ItemsHashRepository.contains(hash_val, feed2.id)

    # 3. Feed 2 saves it -> New row created
    await ItemsHashRepository.save(hash_val, feed2.id)
    assert await ItemsHashRepository.contains(hash_val, feed2.id)

    # Verify we now have 2 rows
    async with Container.get_data().db_session() as session:
        stmt = select(ItemHash).where(ItemHash.hash == hash_val)
        result = await session.execute(stmt)
        items = result.scalars().all()
        assert len(items) == 2
        feed_ids = {i.feed_id for i in items}
        assert feed_ids == {feed1.id, feed2.id}
