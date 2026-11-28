import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode, urlsplit

from app.utils.datetime import parse_datetime


@dataclass(frozen=True)
class SoundCloudTrack:
    id: str
    title: str
    description: str
    date: datetime
    url: str


class SoundCloudClient:
    def __init__(self, get_html: Callable[[str], Awaitable[bytes]]) -> None:
        self.get_html = get_html

    async def get_tracks(self, profile_url: str) -> list[SoundCloudTrack]:
        profile = urlsplit(profile_url)
        parts = profile.path.strip("/").split("/")
        if (
            profile.scheme not in ("http", "https")
            or profile.hostname not in ("soundcloud.com", "www.soundcloud.com")
            or len(parts) not in (1, 2)
            or not re.fullmatch(r"[\w-]+", parts[0])
            or (len(parts) == 2 and parts[1] != "tracks")
        ):
            raise ValueError("Expected a SoundCloud profile URL")
        html = (await self.get_html(f"https://soundcloud.com/{parts[0]}")).decode(
            "utf-8"
        )
        match = re.search(
            r"window\.__sc_hydration\s*=\s*(.*?);\s*</script>", html, re.DOTALL
        )
        if not match:
            raise ValueError("SoundCloud profile hydration is missing")
        try:
            hydration = json.loads(match.group(1))
            user = next(
                entry["data"] for entry in hydration if entry["hydratable"] == "user"
            )
            client = next(
                entry["data"]
                for entry in hydration
                if entry["hydratable"] == "apiClient"
            )
            user_id = str(user["id"])
            client_id = client["id"]
            if (
                not user_id.isdecimal()
                or not isinstance(client_id, str)
                or not client_id
            ):
                raise ValueError("Invalid SoundCloud profile data")
        except (KeyError, TypeError, StopIteration, json.JSONDecodeError) as exc:
            raise ValueError("Invalid SoundCloud profile data") from exc
        query = urlencode(
            {"client_id": client_id, "limit": 50, "linked_partitioning": 1}
        )
        body = await self.get_html(
            f"https://api-v2.soundcloud.com/users/{user_id}/tracks?{query}"
        )
        try:
            collection = json.loads(body)["collection"]
            if not isinstance(collection, list):
                raise TypeError("Invalid SoundCloud track collection")
            tracks = [self._track(entry) for entry in collection]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid SoundCloud track collection") from exc
        return list({track.id: track for track in tracks}.values())

    @staticmethod
    def _track(data: dict) -> SoundCloudTrack:
        track_id = str(data["id"])
        title = data["title"]
        url = data["permalink_url"]
        date = data["display_date"]
        description = data.get("description") or ""
        if (
            not track_id.isdecimal()
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(url, str)
            or urlsplit(url).scheme != "https"
            or urlsplit(url).hostname != "soundcloud.com"
            or not isinstance(date, str)
            or not isinstance(description, str)
        ):
            raise ValueError("Invalid SoundCloud track")
        return SoundCloudTrack(track_id, title, description, parse_datetime(date), url)
