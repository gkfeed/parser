from datetime import datetime


# FIXME: move to core
class FeedUnavailable(Exception):
    def __init__(self, url: str, reason: str, retry_at: datetime | None = None) -> None:
        super().__init__(url)
        self.url = url
        self.reason = reason
        self.retry_at = retry_at

    def __str__(self) -> str:
        return f"Feed unavailable: {self.reason} ({self.url})"
