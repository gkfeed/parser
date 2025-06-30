import json
from datetime import datetime, timedelta


class URLRanker:
    def __init__(self, data_file: str, cooldown_minutes: int = 60):
        self.data_file = data_file
        self.cooldown_minutes = cooldown_minutes
        self.ranks: dict[str, int] = {}
        self.last_failed: dict[str, float] = {}  # timestamp of last failure
        self._load_ranks()

    def _load_ranks(self):
        try:
            with open(self.data_file, "r") as f:
                data = json.load(f)
                self.ranks = data.get("ranks", {})
                self.last_failed = data.get("last_failed", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.ranks = {}
            self.last_failed = {}

    def save_ranks(self):
        with open(self.data_file, "w") as f:
            json.dump(
                {"ranks": self.ranks, "last_failed": self.last_failed}, f, indent=4
            )

    def get_ranked_urls(self, all_urls: list[str]) -> list[str]:
        # Initialize new URLs with a default rank if they don't exist
        for url in all_urls:
            if url not in self.ranks:
                self.ranks[url] = 0  # Default rank

        # Filter out URLs that are in cooldown
        active_urls = []
        for url in all_urls:
            if url in self.last_failed:
                last_fail_time = datetime.fromtimestamp(self.last_failed[url])
                if datetime.now() - last_fail_time < timedelta(
                    minutes=self.cooldown_minutes
                ):
                    continue  # Still in cooldown
            active_urls.append(url)

        # Sort active URLs by rank (lower rank is better)
        active_urls.sort(key=lambda url: self.ranks.get(url, 0))
        return active_urls

    def demote_url(self, url: str):
        self.ranks[url] = self.ranks.get(url, 0) + 1
        self.last_failed[url] = datetime.now().timestamp()
        self.save_ranks()

    def promote_url(self, url: str):
        self.ranks[url] = max(0, self.ranks.get(url, 0) - 1)
        if url in self.last_failed:
            del self.last_failed[url]
        self.save_ranks()
