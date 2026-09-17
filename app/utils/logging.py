import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlsplit, urlunsplit

_context: ContextVar[dict[str, str | int] | None] = ContextVar(
    "log_context", default=None
)


@contextmanager
def log_context(**values: str | int) -> Iterator[None]:
    token = _context.set({**(_context.get() or {}), **values})
    try:
        yield
    finally:
        _context.reset(token)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = _context.get() or {}
        for key in ("feed_id", "task_id", "parser"):
            if not hasattr(record, key):
                setattr(record, key, context.get(key, "-"))
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(ContextFilter())
    formatter = logging.Formatter(
        "%(asctime)sZ %(levelname)s %(name)s "
        "feed_id=%(feed_id)s task_id=%(task_id)s parser=%(parser)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    logging.getLogger("app").setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


def log_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(
        (parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", "")
    )
