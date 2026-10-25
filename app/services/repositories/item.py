from datetime import datetime
from itertools import batched

import structlog
from sqlalchemy import column, select, tuple_, values
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item as _Item
from app.models.item_hash import ItemHash
from app.serializers.feed import Feed, Item

from ._base import BaseRepository
from .feed import FeedRepository
from .feed_parser import FeedParserRepository

logger = structlog.get_logger(__name__)


ItemIdentity = tuple[str, str, str]


class ItemsRepository(BaseRepository):
    # Three parameters per fallback identity, below SQLite's 999-variable limit.
    _lookup_batch_size = 250

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
        known_hashes = await self._known_hashes(session, feed.id, items)
        identities = list(
            dict.fromkeys(
                (item.title, item.link, item.text)
                for item in items
                if not item.hash or item.hash not in known_hashes
            )
        )
        existing_identities = await self._existing_identities(
            session, feed.id, identities
        )
        unseen_items = []
        received = len(items)
        inserted = 0
        known_hash_skipped = 0
        existing_item_skipped = 0
        for item in items:
            if item.hash and item.hash in known_hashes:
                known_hash_skipped += 1
                logger.debug("item_skipped", reason="known_hash")
                continue

            identity = (item.title, item.link, item.text)
            if identity not in existing_identities:
                self._create_item(session, feed, item)
                existing_identities.add(identity)
                inserted += 1
            else:
                existing_item_skipped += 1
                logger.debug("item_skipped", reason="existing_item")

            if item.hash:
                session.add(ItemHash(hash=item.hash, feed_id=feed.id))
                known_hashes.add(item.hash)
            # A new hash is returned even when its fallback identity already exists.
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

    async def _known_hashes(
        self, session: AsyncSession, feed_id: int, items: list[Item]
    ) -> set[str]:
        hashes = list(dict.fromkeys(item.hash for item in items if item.hash))
        known_hashes: set[str] = set()
        for batch in batched(hashes, self._lookup_batch_size):
            result = await session.scalars(
                select(ItemHash.hash).where(
                    ItemHash.feed_id == feed_id, ItemHash.hash.in_(batch)
                )
            )
            known_hashes.update(result)
        return known_hashes

    async def _existing_identities(
        self, session: AsyncSession, feed_id: int, identities: list[ItemIdentity]
    ) -> set[ItemIdentity]:
        # Omitting date from the fallback identity is intentional.
        existing: set[ItemIdentity] = set()
        for batch in batched(identities, self._lookup_batch_size):
            candidates = values(column("title"), column("link"), column("text")).data(
                list(batch)
            )
            result = await session.execute(
                select(_Item.title, _Item.link, _Item.text).where(
                    _Item.feed_id == feed_id,
                    tuple_(_Item.title, _Item.link, _Item.text).in_(candidates),
                )
            )
            existing.update((title, link, text) for title, link, text in result)
        return existing

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
