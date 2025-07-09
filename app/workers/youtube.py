import yt_dlp

from . import worker


@worker
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
