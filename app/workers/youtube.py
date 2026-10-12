from collections.abc import Callable
from typing import Any

import structlog
import yt_dlp

from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)

type InfoResultHandler = Callable[
    [str, dict[str, Any] | None, str | None], dict[str, Any] | None
]


class _YtdlpLogger:
    def __init__(self, url: str) -> None:
        self.logger = logger.bind(**url_log_fields(url))
        self.warnings = 0
        self.errors = 0
        self.last_error: str | None = None

    def debug(self, message: str) -> None:
        self.logger.debug("yt_dlp_message", message=message)

    def warning(self, message: str) -> None:
        self.warnings += 1
        self.logger.warning("yt_dlp_warning", message=message)

    def error(self, message: str) -> None:
        self.errors += 1
        self.last_error = message
        self.logger.error("yt_dlp_error", message=message)

    def log_completion(self) -> None:
        log = self.logger.warning if self.warnings or self.errors else self.logger.info
        log(
            "yt_dlp_extraction_completed",
            warnings=self.warnings,
            errors=self.errors,
        )


async def extract_info(
    url: str,
    opts: Any,
    keys: list[str] | None = None,
    result_handler: InfoResultHandler | None = None,
) -> dict[str, Any]:
    extraction_logger = _YtdlpLogger(url)
    with yt_dlp.YoutubeDL({**opts, "logger": extraction_logger}) as ydl:
        try:
            info: Any = ydl.extract_info(url, download=False)
        finally:
            extraction_logger.log_completion()

    if result_handler is not None:
        info = result_handler(url, info, extraction_logger.last_error)
    if info is None:
        raise ValueError("Could not extract info from URL")
    if (
        result_handler is None
        and extraction_logger.errors
        and info.get("entries") == []
    ):
        raise ValueError("yt-dlp reported errors and returned no entries")
    if keys:
        info = {key: info[key] for key in keys}
    if not info:
        raise ValueError
    return info
