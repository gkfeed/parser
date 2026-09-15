from abc import abstractmethod

from app.core.worker_kind import WorkerKind
from app.serializers.feed import Feed, Item
from app.services.http import HttpClient


class BaseFeed:
    worker_kind = WorkerKind.HEAVY

    def __init__(
        self,
        feed: Feed,
        data: dict,
        *,
        http: HttpClient | None = None,
    ) -> None:
        self.feed = feed
        self.data = data
        self._http = http

    @property
    def http(self) -> HttpClient:
        if self._http is None:
            raise RuntimeError("Parser requires an HttpClient")
        return self._http

    @property
    @abstractmethod
    async def items(self) -> list[Item]:
        pass
