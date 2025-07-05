import hashlib

from app.workers.hash import hash_video_from_url as _hash_video


class HashService:
    @staticmethod
    def hash_str(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    async def hash_video_from_url(video_url: str) -> str:
        return await _hash_video(video_url)
