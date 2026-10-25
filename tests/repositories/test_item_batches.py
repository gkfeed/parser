"""Persistence contracts, also runnable against a disposable canonical PostgreSQL DB.

Set ITEM_BATCH_TEST_DATABASE_URL to a scratch async SQLAlchemy URL after restoring
infra/db/schema.sql. The default boundary is an isolated SQLite database.
"""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base
from app.models.item_hash import ItemHash
from app.serializers.feed import Feed, Item
from app.services.repositories.feed import FeedRepository


@pytest.fixture(
    params=["sqlite", pytest.param("postgresql", marks=pytest.mark.integration)]
)
async def batch_engine(request):
    url = "sqlite+aiosqlite:///:memory:"
    if request.param == "postgresql":
        url = os.environ["ITEM_BATCH_TEST_DATABASE_URL"]
    engine = create_async_engine(url)
    if engine.dialect.name == "sqlite":
        event.listen(engine.sync_engine, "connect", _enable_foreign_keys)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session_factory(batch_engine):
    return async_sessionmaker(batch_engine, expire_on_commit=False)


@pytest.fixture(params=["items", "result"])
def persist_batch(request, items_repository):
    if request.param == "items":
        return items_repository.add_items_to_feed

    async def save(feed, items):
        return await items_repository.save_parser_result(
            feed, items, datetime(2026, 9, 16, tzinfo=UTC)
        )

    return save


def _enable_foreign_keys(connection, _record):
    connection.execute("PRAGMA foreign_keys=ON")


@pytest.fixture
async def create_feed(batch_engine, session_factory):
    user_id = None
    feeds = []
    if batch_engine.dialect.name == "postgresql":
        async with batch_engine.begin() as connection:
            user_id = await connection.scalar(
                text("INSERT INTO users (name) VALUES (:name) RETURNING id"),
                {"name": f"item-batches-{uuid4()}"},
            )

    async def create(title="Batch feed"):
        url = f"https://batch.test/{uuid4()}"
        if user_id is None:
            feed = await FeedRepository(session_factory).create(
                Feed(id=0, title=title, url=url, type="test")
            )
            feeds.append(feed)
            return feed
        async with batch_engine.begin() as connection:
            feed_id = await connection.scalar(
                text(
                    "INSERT INTO feed (title, url, type, user_id) "
                    "VALUES (:title, :url, 'test', :user_id) RETURNING id"
                ),
                {"title": title, "url": url, "user_id": user_id},
            )
        feed = await FeedRepository(session_factory).get_by_id(feed_id)
        feeds.append(feed)
        return feed

    yield create
    for feed in feeds:
        await FeedRepository(session_factory).delete_by_id(feed.id)
    if user_id is not None:
        async with batch_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": user_id}
            )


@pytest.fixture
async def reject_last_hash(batch_engine):
    sqlite = batch_engine.dialect.name == "sqlite"
    if sqlite:
        statements = [
            (
                "CREATE TRIGGER p23_reject_hash BEFORE INSERT ON item_hash "
                "WHEN NEW.hash = 'blocked-batch-hash' "
                "BEGIN SELECT RAISE(ABORT, 'rejected batch hash'); END"
            )
        ]
    else:
        statements = [
            (
                "CREATE FUNCTION p23_reject_hash() RETURNS trigger LANGUAGE plpgsql AS $$ "
                "BEGIN IF NEW.hash = 'blocked-batch-hash' THEN "
                "RAISE EXCEPTION 'rejected batch hash' USING ERRCODE = '23514'; "
                "END IF; RETURN NEW; END; $$"
            ),
            (
                "CREATE TRIGGER p23_reject_hash BEFORE INSERT ON item_hash "
                "FOR EACH ROW EXECUTE FUNCTION p23_reject_hash()"
            ),
        ]
    async with batch_engine.begin() as connection:
        for statement in statements:
            await connection.execute(text(statement))
    yield
    drop_trigger = "DROP TRIGGER p23_reject_hash"
    if not sqlite:
        drop_trigger += " ON item_hash"
    async with batch_engine.begin() as connection:
        await connection.execute(text(drop_trigger))
        if not sqlite:
            await connection.execute(text("DROP FUNCTION p23_reject_hash()"))


def batch_item(index: int) -> Item:
    return Item(
        title=f"Item {index} | unicode café",
        text=f"Body {index}",
        link=f"https://batch.test/items/{index}",
        date=datetime(2026, 9, 15, tzinfo=UTC),
        hash=f"hash-{index}",
    )


async def stored_hashes(session_factory, feed: Feed) -> set[str]:
    async with session_factory() as session:
        return set(
            await session.scalars(
                select(ItemHash.hash).where(ItemHash.feed_id == feed.id)
            )
        )


async def test_large_batch_preserves_order_and_deduplicates_across_batches(
    create_feed, items_repository, persist_batch, session_factory
):
    feed = await create_feed()
    items = [batch_item(index) for index in range(605)]
    alias = items[0].model_copy(update={"hash": "alternate-hash-0"})
    same_hash_changed_identity = items[0].model_copy(
        update={"title": "Hash takes precedence"}
    )
    incoming = (
        items[:300]
        + items[:5]
        + items[300:]
        + [items[0], items[400], alias, same_hash_changed_identity]
    )

    assert await persist_batch(feed, incoming) == items + [alias]
    saved = await items_repository.get_all(feed)
    assert {item.link for item in saved} == {item.link for item in items}
    assert len(saved) == len(items)
    assert await stored_hashes(session_factory, feed) == {
        item.hash for item in items
    } | {alias.hash}
    assert await persist_batch(feed, incoming) == []


async def test_fallback_identity_ignores_date_and_retains_new_hash_results(
    create_feed, items_repository, persist_batch, session_factory
):
    feed = await create_feed()
    original = batch_item(0)
    await persist_batch(feed, [original])
    changed_date = original.model_copy(
        update={"date": original.date + timedelta(days=1), "hash": "new-hash"}
    )
    unhashed = original.model_copy(update={"hash": None})
    changed_title = original.model_copy(update={"title": "New title", "hash": None})
    changed_link = original.model_copy(
        update={"link": "https://batch.test/new", "hash": None}
    )
    changed_text = original.model_copy(update={"text": "New body", "hash": None})
    incoming = [
        changed_date,
        changed_date,
        unhashed,
        unhashed,
        changed_title,
        changed_link,
        changed_text,
    ]

    assert await persist_batch(feed, incoming) == [
        changed_date,
        unhashed,
        unhashed,
        changed_title,
        changed_link,
        changed_text,
    ]
    assert len(await items_repository.get_all(feed)) == 4
    assert await stored_hashes(session_factory, feed) == {"hash-0", "new-hash"}
    assert await persist_batch(feed, [changed_date]) == []


async def test_batch_identities_and_hashes_are_scoped_without_claiming_legacy_hashes(
    create_feed,
    items_repository,
    persist_batch,
    session_factory,
):
    first = await create_feed("First feed")
    second = await create_feed("Second feed")
    items = [batch_item(index) for index in range(3)]
    await persist_batch(first, items)
    legacy_rows = [
        ItemHash(hash="hash-0", feed_id=None),
        ItemHash(hash="hash-0", feed_id=None),
    ]
    async with session_factory() as session, session.begin():
        session.add_all(legacy_rows)
    legacy_ids = [row.id for row in legacy_rows]

    assert await persist_batch(second, items) == items
    assert len(await items_repository.get_all(second)) == 3
    async with session_factory() as session:
        legacy = list(
            await session.scalars(
                select(ItemHash).where(
                    ItemHash.id.in_(legacy_ids), ItemHash.feed_id.is_(None)
                )
            )
        )
    assert len(legacy) == 2
    assert {row.hash for row in legacy} == {"hash-0"}
    async with session_factory() as session, session.begin():
        await session.execute(delete(ItemHash).where(ItemHash.id.in_(legacy_ids)))


async def test_existing_duplicate_rows_do_not_break_batch_matching(
    create_feed, items_repository, persist_batch, session_factory
):
    feed = await create_feed()
    item = batch_item(0).model_copy(update={"hash": None})
    await persist_batch(feed, [item])
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO item (feed_id, title, link, text, date) "
                "SELECT feed_id, title, link, text, date FROM item WHERE feed_id = :id"
            ),
            {"id": feed.id},
        )

    hashed = item.model_copy(update={"hash": "new-hash"})
    assert await persist_batch(feed, [hashed, hashed]) == [hashed]
    assert len(await items_repository.get_all(feed)) == 2
    assert await stored_hashes(session_factory, feed) == {"new-hash"}


async def test_batch_rolls_back_after_late_hash_failure_and_can_retry(
    create_feed, reject_last_hash, items_repository, persist_batch, session_factory
):
    feed = await create_feed()
    items = [batch_item(index) for index in range(605)]
    items[-1] = items[-1].model_copy(update={"hash": "blocked-batch-hash"})
    with pytest.raises(IntegrityError, match="rejected batch hash"):
        await persist_batch(feed, items)

    assert await items_repository.get_all(feed) == []
    assert await stored_hashes(session_factory, feed) == set()
    items[-1] = batch_item(604)
    assert await persist_batch(feed, items) == items
    assert len(await items_repository.get_all(feed)) == 605
    assert await persist_batch(feed, items) == []


async def test_empty_batch_and_unhashed_batch_with_stored_identities(
    create_feed, items_repository, persist_batch, session_factory
):
    feed = await create_feed()
    assert await persist_batch(feed, []) == []
    items = [
        batch_item(index).model_copy(update={"hash": None}) for index in range(605)
    ]
    incoming = items + items[:3]
    assert await persist_batch(feed, incoming) == incoming
    assert await persist_batch(feed, incoming) == incoming
    assert len(await items_repository.get_all(feed)) == 605
    assert await stored_hashes(session_factory, feed) == set()
