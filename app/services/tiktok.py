from app.services.youtube import YoutubeInfoExtractor


class TikTokInfoExtractor(YoutubeInfoExtractor):
    _max_videos = 30
    _ydl_opts_tab = {
        'ignoreerrors': True,
        'quiet': True,
        'lazy_playlist': False,
        'extract_flat': True,
        'playlist_items': f'1-{_max_videos}',
    }
