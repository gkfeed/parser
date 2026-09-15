from datetime import timedelta
from typing import override

from app.serializers.feed import Feed
from app.services.http import HttpClient

from .base import BaseFeed as _BaseFeed


class CacheFeedExtension(_BaseFeed):
    _cache_storage_time = timedelta(minutes=5)
    _cache_storage_time_if_success = timedelta(hours=1)

    @override
    def __init__(
        self,
        feed: Feed,
        data: dict,
        *,
        http: HttpClient | None = None,
    ) -> None:
        data["cache_storage_time"] = self._cache_storage_time
        data["cache_storage_time_if_success"] = self._cache_storage_time_if_success
        super().__init__(feed, data, http=http)
