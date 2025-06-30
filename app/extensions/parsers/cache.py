from typing import override
from datetime import timedelta

from app.serializers.feed import Feed
from .base import BaseFeed as _BaseFeed


class CacheFeedExtension(_BaseFeed):
    _cache_storage_time = timedelta(minutes=5)
    _cache_storage_time_if_success = timedelta(hours=1)

    @override
    def __init__(self, feed: Feed, data: dict) -> None:
        data["cache_storage_time"] = self._cache_storage_time
        data["cache_storage_time_if_success"] = self._cache_storage_time_if_success
        super().__init__(feed, data)
