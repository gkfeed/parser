from ._base import BaseMiddleware
from .log import LoggingMiddleware
from .failed import FailedFeedMiddleware

MIDDLEWARES: list[BaseMiddleware] = [LoggingMiddleware(), FailedFeedMiddleware()]
