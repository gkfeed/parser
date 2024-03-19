from ._base import BaseMiddleware
from .log import LoggingMiddleware

MIDDLEWARES: list[BaseMiddleware] = [LoggingMiddleware()]
