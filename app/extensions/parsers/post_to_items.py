import logging
from abc import ABC, abstractmethod
from datetime import datetime

from bs4 import Tag

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime

logger = logging.getLogger(__name__)


class PostToItemsMixin(ABC):
    # When True, malformed posts are skipped instead of aborting the feed.
    # Defaults to False so page structure changes fail loudly.
    skip_invalid_posts: bool = False
    skip_post_exceptions: tuple[type[BaseException], ...] = (
        ValueError,
        IndexError,
    )

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

    async def _post_to_item(self, post: Tag) -> Item:
        return Item(
            title=await self._get_post_title(post),
            text=await self._get_post_text(post),
            date=await self._get_post_datetime(post),
            link=await self._get_post_link(post),
        )

    @property
    async def items(self) -> list[Item]:
        items: list[Item] = []
        for post in await self._posts:
            try:
                items.append(await self._post_to_item(post))
            except self.skip_post_exceptions as exc:
                if not self.skip_invalid_posts:
                    raise
                logger.warning("Skipping malformed post: %s", exc)
        return items
