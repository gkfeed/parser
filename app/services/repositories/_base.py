from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory
