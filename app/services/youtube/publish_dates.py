from datetime import UTC, datetime
from xml.etree import ElementTree

from app.services.http import HttpService


class YoutubePublishDateService:
    _channel_feed_url = "https://www.youtube.com/feeds/videos.xml?channel_id={}"

    @classmethod
    async def get_channel_publish_dates(
        cls, channel_id: str
    ) -> dict[str, datetime]:
        xml = await HttpService.get(cls._channel_feed_url.format(channel_id))
        root = ElementTree.fromstring(xml)
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        publish_dates = {}

        for entry in root.findall("atom:entry", namespaces):
            video_id = entry.findtext("yt:videoId", namespaces=namespaces)
            published = entry.findtext("atom:published", namespaces=namespaces)
            if video_id and published:
                publish_dates[video_id] = datetime.fromisoformat(published)

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
