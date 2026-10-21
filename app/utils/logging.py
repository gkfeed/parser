import logging
import os
from urllib.parse import urlsplit, urlunsplit

import structlog

LOG_FORMATS = ("logfmt", "json")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def configure_logging() -> None:
    log_format = os.getenv("LOG_FORMAT", "logfmt").lower()
    if log_format not in LOG_FORMATS:
        supported = ", ".join(LOG_FORMATS)
        raise ValueError(
            f"Invalid LOG_FORMAT={log_format!r}; expected one of: {supported}"
        )

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    if log_level not in LOG_LEVELS:
        supported = ", ".join(LOG_LEVELS)
        raise ValueError(
            f"Invalid LOG_LEVEL={log_level!r}; expected one of: {supported}"
        )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer: structlog.types.Processor
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.processors.LogfmtRenderer(
            key_order=(
                "timestamp",
                "level",
                "logger",
                "event",
                "feed_id",
                "task_id",
                "parser",
            ),
            drop_missing=True,
            bool_as_flag=False,
        )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)
    logging.getLogger("app").setLevel(log_level)


def url_log_fields(url: str, *, field: str = "url") -> dict[str, str]:
    try:
        parts = urlsplit(url)
    except Exception as exc:  # noqa: BLE001 - logging must not mask the real failure
        return {field: "<invalid-url>", f"{field}_error": type(exc).__name__}

    sanitized = urlunsplit(
        (parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", "")
    )
    return {field: sanitized}
