from typing import Any

import yt_dlp


async def extract_info(
    url: str, opts: Any, keys: list[str] | None = None
) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(opts) as ydl:
        info: Any = ydl.extract_info(url, download=False)
        if info is None:
            raise ValueError("Could not extract info from URL")
        if keys:
            info = {key: info[key] for key in keys}
    if not info:
        raise ValueError
    return info
