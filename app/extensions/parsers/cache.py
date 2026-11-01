from datetime import timedelta

from .base import BaseFeed as _BaseFeed


class CacheFeedExtension(_BaseFeed):
    empty_result_delay = timedelta(minutes=5)
    success_result_delay = timedelta(hours=1)
