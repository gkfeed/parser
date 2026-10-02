import structlog

from app.services.catbox import CatboxUploader
from app.services.tempfile import TempFileUploader
from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)


class FallbackUploader:
    uploaders = (CatboxUploader, TempFileUploader)

    @classmethod
    async def upload_with_url(cls, url: str) -> str | None:
        for uploader in cls.uploaders:
            try:
                return await uploader.upload_with_url(url)
            except Exception as exc:  # noqa: BLE001 - try the next uploader
                logger.warning(
                    "media_upload_failed",
                    uploader=uploader.__name__,
                    error_type=type(exc).__name__,
                    **url_log_fields(url),
                )

        return None
