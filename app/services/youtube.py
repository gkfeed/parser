from datetime import timedelta

import yt_dlp

from app.services.queue import QueueService
from app.services.cache.use_temporary import (
    UseTemporaryCacheServiceExtension, async_store_in_cache_for)


class YoutubeInfoExtractor(UseTemporaryCacheServiceExtension):
    _channel_info_storage_time = timedelta(hours=1)
    _video_info_storage_time = timedelta(weeks=1)
    _max_videos = 5
    _ydl_opts_tab = {
        'ignoreerrors': True,
        'quiet': True,
        'lazy_playlist': False,
        'extract_flat': True,
        'playlist_items': f'1-{_max_videos}',
        'extractor_args': {'youtubetab': {
            'approximate_date': 'upload_date',
        }},
    }
    _ydl_opts_video = {
        'ignoreerrors': True,
        'quiet': True,
        'extract_flat': False,
        'skip_download': True,
        'extractorargs': {
            'youtube': {
                'player_skip': ['js', 'webpage', 'configs'],
                'skip': ['hls', 'dash', 'translated_tabs'],
            }
        }
    }

    @classmethod
    @async_store_in_cache_for(_video_info_storage_time)
    async def get_video_info(cls, url: str) -> dict:
        return await QueueService.put_and_wait_for_result(
            cls.extract_info, [url, cls._ydl_opts_video])

    @classmethod
    @async_store_in_cache_for(_channel_info_storage_time)
    async def get_page_info(cls, url: str) -> dict:
        return await QueueService.put_and_wait_for_result(
            cls.extract_info, [url, cls._ydl_opts_tab])

    @classmethod
    def extract_info(cls, url: str, opts: dict = _ydl_opts_tab) -> dict:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError
        return info
