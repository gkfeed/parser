from ._base import BaseMiddleware
from .log import LoggingMiddleware
from .failed import FailedFeedMiddleware
from .cache import CacheMiddleware

MIDDLEWARES: list[BaseMiddleware] = [
    CacheMiddleware(),
    LoggingMiddleware(),
    FailedFeedMiddleware(),
]
