from datetime import UTC, datetime
from xml.etree import ElementTree

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.http import HttpRequestError, HttpService


class YoutubePublishDateService:
    _channel_feed_url = "https://www.youtube.com/feeds/videos.xml?channel_id={}"

    @classmethod
    async def get_channel_publish_dates(cls, channel_id: str) -> dict[str, datetime]:
        url = cls._channel_feed_url.format(channel_id)
        try:
            xml = await HttpService.get(url)
        except HttpRequestError as exc:
            raise FeedUnavailable(url, "youtube_publish_dates_request_failed") from exc
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError as exc:
            raise ValueError(
                f"Invalid YouTube Atom XML for channel {channel_id}"
            ) from exc
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        if root.tag != f"{{{namespaces['atom']}}}feed":
            raise ValueError(f"Expected a YouTube Atom feed for channel {channel_id}")
        publish_dates = {}

        for entry in root:
            if entry.tag.rsplit("}", 1)[-1] != "entry":
                continue
            if entry.tag != f"{{{namespaces['atom']}}}entry":
                raise ValueError("YouTube Atom entry has an invalid namespace")
            video_id = entry.findtext(
                "yt:videoId", namespaces=namespaces, default=""
            ).strip()
            published = entry.findtext(
                "atom:published", namespaces=namespaces, default=""
            ).strip()
            if not video_id or not published:
                raise ValueError("YouTube Atom entry requires videoId and published")
            try:
                published_at = datetime.fromisoformat(published)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid YouTube Atom published date for video {video_id}: {published!r}"
                ) from exc
            if published_at.tzinfo is None:
                raise ValueError(
                    f"YouTube Atom published date has no timezone for video {video_id}"
                )
            publish_dates[video_id] = published_at

        return publish_dates

    @staticmethod
    def resolve(
        video_info: dict, channel_publish_dates: dict[str, datetime]
    ) -> datetime | None:
        if published_at := channel_publish_dates.get(video_info.get("id", "")):
            return published_at

        if (timestamp := video_info.get("timestamp")) is not None:
            return datetime.fromtimestamp(timestamp, tz=UTC)

        if upload_date := video_info.get("upload_date"):
            return datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=UTC)

        return None
