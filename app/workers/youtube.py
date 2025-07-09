import yt_dlp


# class VideoInfo(NamedTuple):
#     title: str
#     upload_date_str: str
#     channel_name: str
#
#
# @worker
# async def extract_video_urls(
#     videos_url: str, extraction_mode: BaseExtractionMode, max_videos: int
# ) -> list[str]:
#     info = await YoutubeInfoExtractor.get_info(videos_url, extraction_mode)
#     return [v["url"] for v in info["entries"][-max_videos:]]
#
#
# @worker
# async def extract_video_info(url: str) -> VideoInfo:
#     info = await YoutubeInfoExtractor.get_info(url, VideoExtractionMode())
#     return VideoInfo(info["title"], info["upload_date"], info["uploader"])
#
#
# # FIXME: max_videos unused
# @worker
# async def extract_channel_videos_info(
#     videos_url: str, extraction_mode: BaseExtractionMode, max_videos: int
# ) -> dict:
#     return await YoutubeInfoExtractor.get_info(videos_url, extraction_mode)


def extract_info(url: str, opts: dict, keys: list[str] | None = None) -> dict:
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise ValueError("Could not extract info from URL")
        if keys:
            _info = {}
            for key in keys:
                _info[key] = info[key]
            info = _info
    if not info:
        raise ValueError
    return info
