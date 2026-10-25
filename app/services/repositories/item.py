from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item as _Item
from app.models.item_hash import ItemHash
from app.serializers.feed import Feed, Item

from ._base import BaseRepository
from .feed import FeedRepository
from .feed_parser import FeedParserRepository

logger = structlog.get_logger(__name__)


class ItemsRepository(BaseRepository):
    async def get_all(self, feed: Feed) -> list[Item]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(_Item).where(_Item.feed_id == feed.id)
            )
            return [self._serialize_item(i) for i in result.scalars().all()]

    async def add_items_to_feed(self, feed: Feed, items: list[Item]) -> list[Item]:
        async with self._session_factory() as session, session.begin():
            return await self.add_items_in_session(session, feed, items)

    async def save_parser_result(
        self, feed: Feed, items: list[Item], valid_for: datetime
    ) -> list[Item]:
        """Commit items, hashes and parser state together, or discard a deleted feed."""
        async with self._session_factory() as session, session.begin():
            if not await FeedRepository.lock_in_session(session, feed.id):
                logger.info("parser_result_discarded", reason="feed_deleted")
                return []
            unseen_items = await self.add_items_in_session(session, feed, items)
            await FeedParserRepository.upsert_in_session(session, feed.id, valid_for)
        return unseen_items

    async def add_items_in_session(
        self, session: AsyncSession, feed: Feed, items: list[Item]
    ) -> list[Item]:
        """Write items and hashes without committing the caller's transaction."""
        unseen_items = []
        received = len(items)
        inserted = 0
        known_hash_skipped = 0
        existing_item_skipped = 0
        for item in items:
            if item.hash and await self._contains_hash(session, item.hash, feed.id):
                known_hash_skipped += 1
                logger.debug("item_skipped", reason="known_hash")
                continue

            if not await self._check_if_exists(session, feed, item):
                self._create_item(session, feed, item)
                inserted += 1
            else:
                existing_item_skipped += 1
                logger.debug("item_skipped", reason="existing_item")

            if item.hash:
                session.add(ItemHash(hash=item.hash, feed_id=feed.id))
            unseen_items.append(item)

        logger.info(
            "items_prepared",
            received=received,
            inserted=inserted,
            known_hash_skipped=known_hash_skipped,
            existing_item_skipped=existing_item_skipped,
            returned=len(unseen_items),
        )
        return unseen_items

    @staticmethod
    async def _contains_hash(session: AsyncSession, hash: str, feed_id: int) -> bool:
        stmt = select(ItemHash).where(
            ItemHash.hash == hash, ItemHash.feed_id == feed_id
        )
        result = await session.execute(stmt)
        return result.scalars().first() is not None

    @staticmethod
    async def _check_if_exists(session: AsyncSession, feed: Feed, item: Item) -> bool:
        # Omitting date from the fallback identity is intentional.
        stmt = select(_Item).where(
            _Item.feed_id == feed.id,
            _Item.title == item.title,
            _Item.link == item.link,
            _Item.text == item.text,
        )
        existing = (await session.execute(stmt)).scalars().first()
        return existing is not None

    @staticmethod
    def _create_item(session: AsyncSession, feed: Feed, item: Item) -> None:
        new_item = _Item(
            feed_id=feed.id,
            title=item.title,
            text=item.text,
            date=item.date,
            link=item.link,
        )
        session.add(new_item)

    @staticmethod
    def _serialize_item(model_item: _Item) -> Item:
        return Item(
            title=model_item.title,
            text=model_item.text,
            date=model_item.date,
            link=model_item.link,
        )
