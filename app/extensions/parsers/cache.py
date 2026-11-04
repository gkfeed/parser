from datetime import timedelta

from .base import BaseFeed as _BaseFeed


class CacheFeedExtension(_BaseFeed):
    _cache_storage_time = timedelta(minutes=5)
    _cache_storage_time_if_success = timedelta(hours=1)
