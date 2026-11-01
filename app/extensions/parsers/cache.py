from datetime import timedelta

from .base import BaseFeed as _BaseFeed


class CacheFeedExtension(_BaseFeed):
    """Scheduling intervals consumed by the dispatcher without parser construction."""

    _cache_storage_time: timedelta = timedelta(minutes=5)
    _cache_storage_time_if_success: timedelta = timedelta(hours=1)
