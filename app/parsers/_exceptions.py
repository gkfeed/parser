class UnavailableFeed(Exception):
    def __init__(self, url: str) -> None:
        self.url = url

    def __str__(self) -> str:
        return ('Feed is currently unavailable check if url is accessible: '
                + self.url)
