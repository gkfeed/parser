from abc import ABC, abstractmethod
from datetime import datetime

from bs4 import Tag

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime


class PostToItemsMixin(ABC):
    @property
    @abstractmethod
    async def _posts(self) -> list[Tag]:
        pass

    @abstractmethod
    async def _get_post_title(self, post: Tag) -> str:
        pass

    async def _get_post_text(self, post: Tag) -> str:
        return await self._get_post_title(post)

    @abstractmethod
    async def _get_post_link(self, post: Tag) -> str:
        pass

    async def _get_post_datetime(self, post: Tag) -> datetime:
        return constant_datetime

    @property
    async def items(self) -> list[Item]:
        return [
            Item(
                title=await self._get_post_title(p),
                text=await self._get_post_text(p),
                date=await self._get_post_datetime(p),
                link=await self._get_post_link(p),
            )
            for p in await self._posts
        ]
