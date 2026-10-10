from datetime import datetime


# FIXME: move to core
class UnavailableFeed(Exception):
    def __init__(self, url: str) -> None:
        self.url = url

    def __str__(self) -> str:
        return "Feed is currently unavailable check if url is accessible: " + self.url


class FeedUnavailable(UnavailableFeed):
    def __init__(self, url: str, reason: str, retry_at: datetime | None = None) -> None:
        super().__init__(url)
        self.reason = reason
        self.retry_at = retry_at

    def __str__(self) -> str:
        return f"Feed unavailable: {self.reason} ({self.url})"
