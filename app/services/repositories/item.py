from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.item import Item as _Item
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
    async def add_items_to_feed(cls, feed: Feed, items: list[Item]):
        async with cls._session_factory() as session:
            async with session.begin():
                for item in items:
                    if not await cls._check_if_exists(session, feed, item):
                        await cls._create_item(session, feed, item)

    @classmethod
    async def _check_if_exists(cls, session: AsyncSession, feed: Feed, item: Item) -> bool:
        stmt = select(_Item).where(
            _Item.feed_id == feed.id,
            _Item.title == item.title,
            _Item.link == item.link,
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