from ._base import BaseMiddleware
from .log import LoggingMiddleware
from .failed import FailedFeedMiddleware
from .cache import CacheMiddleware
from .hash import HashMiddleware
from .feed_rank import FeedRankMiddleware

MIDDLEWARES: list[BaseMiddleware] = [
    CacheMiddleware(),
    LoggingMiddleware(),
    HashMiddleware(),
    FailedFeedMiddleware(),
    FeedRankMiddleware(),
]
