from ._base import BaseMiddleware
from .log import LoggingMiddleware
from .failed import FailedFeedMiddleware
from .cache import CacheMiddleware
from .hash import HashMiddleware

MIDDLEWARES: list[BaseMiddleware] = [
    CacheMiddleware(),
    LoggingMiddleware(),
    HashMiddleware(),
    FailedFeedMiddleware(),
]
