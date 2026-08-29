import logging

from app.services.catbox import CatboxUploader
from app.services.tempfile import TempFileUploader

logger = logging.getLogger(__name__)


class FallbackUploader:
    uploaders = (CatboxUploader, TempFileUploader)

    @classmethod
    async def upload_with_url(cls, url: str) -> str | None:
        for uploader in cls.uploaders:
            try:
                return await uploader.upload_with_url(url)
            except Exception:  # noqa: BLE001 - try the next uploader
                logger.warning("Uploader %s failed for %s", uploader.__name__, url)

        return None
