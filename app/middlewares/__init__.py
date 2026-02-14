from ._base import BaseMiddleware
from .log import LoggingMiddleware
from .failed import FailedFeedMiddleware
from .cache import CacheMiddleware
from .feed_rank import FeedRankMiddleware

# TODO: middlewares not used
MIDDLEWARES: list[BaseMiddleware] = [
    CacheMiddleware(),
    LoggingMiddleware(),
    FailedFeedMiddleware(),
    FeedRankMiddleware(),
]
