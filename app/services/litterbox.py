import mimetypes
import re
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import aiohttp

from app.services.http import HttpService


class LitterboxUploadError(Exception):
    """Litterbox could not upload the source file."""


class LitterboxUploader:
    host_url = "https://litterbox.catbox.moe/resources/internals/api.php"
    max_file_size = 1024 * 1024 * 1024

    @classmethod
    async def upload_with_url(cls, url: str) -> str:
        timeout = aiohttp.ClientTimeout(total=120)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(url, headers=HttpService.headers) as source,
        ):
            source.raise_for_status()
            if (
                source.content_length is not None
                and source.content_length > cls.max_file_size
            ):
                raise LitterboxUploadError(
                    "Source file exceeds Litterbox's size limit"
                )

            suffix = mimetypes.guess_extension(source.content_type)
            if not suffix or source.content_type == "application/octet-stream":
                suffix = PurePosixPath(urlsplit(str(source.url)).path).suffix or suffix
            if not re.fullmatch(r"\.[a-zA-Z0-9]{1,10}", suffix or ""):
                raise LitterboxUploadError("Cannot determine source file extension")

            form = aiohttp.FormData()
            form.add_field("reqtype", "fileupload")
            form.add_field("time", "72h")
            form.add_field(
                "fileToUpload",
                cls._file_chunks(source),
                filename=f"media{suffix}",
                content_type=source.content_type,
            )
            async with session.post(
                cls.host_url, data=form, headers=HttpService.headers
            ) as response:
                response.raise_for_status()
                uploaded_url = (await response.text()).strip()

        if not uploaded_url.startswith("https://litter.catbox.moe/"):
            raise LitterboxUploadError("Litterbox did not return an uploaded file URL")
        return uploaded_url

    @classmethod
    async def _file_chunks(
        cls, response: aiohttp.ClientResponse
    ) -> AsyncIterator[bytes]:
        size = 0
        async for chunk in response.content.iter_chunked(65536):
            size += len(chunk)
            if size > cls.max_file_size:
                raise LitterboxUploadError("Source file exceeds Litterbox's size limit")
            yield chunk
