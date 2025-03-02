import hashlib

import requests

from . import worker


@worker
async def hash_video_from_url(
    url: str, algorithm: str = "sha256", chunk_size: int = 8192
) -> str:
    hasher = hashlib.new(algorithm)

    try:
        with requests.get(url, stream=True, timeout=10) as response:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    hasher.update(chunk)
        return hasher.hexdigest()

    except requests.exceptions.RequestException as e:
        raise requests.RequestException(f"Failed to fetch URL: {e}")
    except ValueError as e:
        raise ValueError(f"Invalid hashing algorithm: {algorithm}") from e
