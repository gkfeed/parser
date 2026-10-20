import asyncio
import base64
from dataclasses import dataclass
from functools import cached_property
from io import BytesIO

from PIL import Image, ImageOps

from app.services.http import HttpRequestError, HttpService


class ImageResponseError(HttpRequestError):
    """The image source returned an error status or a non-image response."""

    def __init__(self, status: int, content_type: str) -> None:
        super().__init__("Invalid image response", status=status)
        self.content_type = content_type


@dataclass(frozen=True)
class EmbeddedImage:
    """Image bytes, MIME type and their embedded data URL representation."""

    content: bytes
    mime_type: str

    @cached_property
    def encoded(self) -> str:
        return base64.b64encode(self.content).decode("utf-8")

    @property
    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{self.encoded}"

    @classmethod
    def from_base64(cls, mime_type: str, encoded: str) -> "EmbeddedImage":
        try:
            content = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError(f"Invalid base64 image: {exc}") from exc
        return cls(content, mime_type)


class ImageService:
    """Prepare embedded images without feed, item or deduplication state.

    Downloads are limited to 20 MiB and images to 20 million pixels. Source
    failures raise HttpRequestError or ImageResponseError; invalid image data
    raises ValueError. Pillow work runs in a thread.
    """

    _max_download_bytes = 20 * 1024 * 1024
    _max_image_pixels = 20_000_000

    @classmethod
    async def download(cls, url: str) -> EmbeddedImage:
        response = await HttpService.get_response(
            url, max_bytes=cls._max_download_bytes
        )
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if response.status >= 400 or not content_type.startswith("image/"):
            raise ImageResponseError(response.status, content_type)
        return await cls.from_content(response.content)

    @classmethod
    async def from_content(cls, content: bytes) -> EmbeddedImage:
        """Validate existing image bytes without re-encoding their content."""
        try:
            mime_type = await asyncio.to_thread(cls._validate_image, content)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ValueError(f"Invalid image: {exc}") from exc
        return EmbeddedImage(content, mime_type)

    @classmethod
    async def resize(cls, image: EmbeddedImage, budget: int) -> EmbeddedImage:
        """Return an EXIF-oriented RGB JPEG, targeting budget bytes.

        The smallest thumbnail at quality 40 may still exceed the budget.
        """
        try:
            content = await asyncio.to_thread(cls._resize_image, image.content, budget)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ValueError(f"Cannot resize image: {exc}") from exc
        return EmbeddedImage(content, "image/jpeg")

    @classmethod
    def _validate_image(cls, data: bytes) -> str:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > cls._max_image_pixels:
                raise ValueError("Image exceeds pixel limit")
            mime_type = Image.MIME.get(image.format or "")
            if mime_type is None:
                raise ValueError("Unknown image format")
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
        return mime_type

    @classmethod
    def _resize_image(cls, data: bytes, budget: int) -> bytes:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > cls._max_image_pixels:
                raise ValueError("Image exceeds pixel limit")
            image = ImageOps.exif_transpose(source).convert("RGB")
        while True:
            content = cls._try_encode_jpeg(image, budget)
            if content is not None:
                return content
            image.thumbnail(
                (max(128, image.width * 3 // 4), max(128, image.height * 3 // 4))
            )

    @staticmethod
    def _try_encode_jpeg(image: Image.Image, budget: int) -> bytes | None:
        """Return the first JPEG within budget, or None if resizing is needed.

        At a longest side of 128 px or less, return quality 40 even over budget.
        """
        for quality in (85, 70, 55, 40):
            output = BytesIO()
            image.save(output, format="JPEG", quality=quality, optimize=True)
            content = output.getvalue()
            if len(content) <= budget or (max(image.size) <= 128 and quality == 40):
                return content
        return None
