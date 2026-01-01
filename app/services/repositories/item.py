from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.models.item import Item as _Item
from app.serializers.feed import Feed, Item
from app.utils.inject import inject


class ItemsRepository:
    def __init__(self, feed: Feed):
        self.feed = feed

    @inject({"session_factory": "db_session"})
    async def get_all(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> list[Item]:
        async with session_factory() as session:
            result = await session.execute(
                select(_Item).where(_Item.feed_id == self.feed.id)
            )
            return [self._serialize_item(i) for i in result.scalars().all()]

    @inject({"session_factory": "db_session"})
    async def add_items_to_feed(
        self, items: list[Item], session_factory: async_sessionmaker[AsyncSession]
    ):
        async with session_factory() as session:
            async with session.begin():
                for item in items:
                    if not await self._check_if_exists(session, item):
                        await self._create_item(session, item)

    async def _check_if_exists(self, session: AsyncSession, item: Item) -> bool:
        stmt = select(_Item).where(
            _Item.feed_id == self.feed.id,
            _Item.title == item.title,
            _Item.link == item.link,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()
        return existing is not None

    async def _create_item(self, session: AsyncSession, item: Item) -> None:
        new_item = _Item(
            feed_id=self.feed.id,
            title=item.title,
            text=item.text,
            date=item.date,
            link=item.link,
        )
        session.add(new_item)

    def _serialize_item(self, model_item: _Item) -> Item:
        return Item(
            title=model_item.title,
            text=model_item.text,
            date=model_item.date,
            link=model_item.link,
        )
