from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item as _Item
from app.models.item_hash import ItemHash
from app.serializers.feed import Feed, Item

from ._base import BaseRepository


class ItemsRepository(BaseRepository):
    @classmethod
    async def get_all(cls, feed: Feed) -> list[Item]:
        async with cls._session_factory() as session:
            result = await session.execute(
                select(_Item).where(_Item.feed_id == feed.id)
            )
            return [cls._serialize_item(i) for i in result.scalars().all()]

    @classmethod
    async def add_items_to_feed(cls, feed: Feed, items: list[Item]) -> list[Item]:
        unseen_items = []
        async with cls._session_factory() as session, session.begin():
            for item in items:
                if item.hash and await cls._contains_hash(session, item.hash, feed.id):
                    continue

                if not await cls._check_if_exists(session, feed, item):
                    await cls._create_item(session, feed, item)

                if item.hash:
                    session.add(ItemHash(hash=item.hash, feed_id=feed.id))
                unseen_items.append(item)

        return unseen_items

    @staticmethod
    async def _contains_hash(
        session: AsyncSession, hash: str, feed_id: int
    ) -> bool:
        stmt = select(ItemHash).where(
            ItemHash.hash == hash, ItemHash.feed_id == feed_id
        )
        result = await session.execute(stmt)
        return result.scalars().first() is not None

    @classmethod
    async def _check_if_exists(
        cls, session: AsyncSession, feed: Feed, item: Item
    ) -> bool:
        # Omitting date from the fallback identity is intentional.
        stmt = select(_Item).where(
            _Item.feed_id == feed.id,
            _Item.title == item.title,
            _Item.link == item.link,
            _Item.text == item.text,
        )
        existing = (await session.execute(stmt)).scalars().first()
        return existing is not None

    @classmethod
    async def _create_item(cls, session: AsyncSession, feed: Feed, item: Item) -> None:
        new_item = _Item(
            feed_id=feed.id,
            title=item.title,
            text=item.text,
            date=item.date,
            link=item.link,
        )
        session.add(new_item)

    @classmethod
    def _serialize_item(cls, model_item: _Item) -> Item:
        return Item(
            title=model_item.title,
            text=model_item.text,
            date=model_item.date,
            link=model_item.link,
        )
