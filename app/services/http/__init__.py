from dataclasses import dataclass

import aiohttp
from aiohttp.client_exceptions import ClientConnectorError, ClientError, InvalidURL

from .lifecycle import HttpSessionScope

_headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        "AppleWebKit/537.36 (KHTML, like Gecko)"
        "Chrome/106.0.0.0 Safari/537.36"
    ),
}


class HttpRequestError(Exception):
    "Http request error"

    def __init__(self, message: str = "HTTP request failed", status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class HttpResponse:
    status: int
    content: bytes
    headers: dict[str, str]


class HttpService(HttpSessionScope):
    headers = _headers

    @classmethod
    async def get(cls, url: str, headers: dict = headers) -> bytes:
        status, content = await cls.get_with_status(url, headers=headers)
        if status >= 400:
            raise HttpRequestError(
                f"HTTP request failed with status {status}", status=status
            )
        return content

    @classmethod
    async def get_with_status(
        cls, url: str, headers: dict = headers
    ) -> tuple[int, bytes]:
        response = await cls.get_response(url, headers=headers)
        return response.status, response.content

    @classmethod
    async def get_response(
        cls, url: str, headers: dict = headers, max_bytes: int | None = None
    ) -> HttpResponse:
        try:
            async with (
                cls.session() as session,
                session.get(url, headers=headers) as response,
            ):
                content = await cls._read_content(response, max_bytes)
                return HttpResponse(
                    response.status,
                    content,
                    {key.lower(): value for key, value in response.headers.items()},
                )
        except (ClientError, TimeoutError) as exc:
            raise HttpRequestError(status=getattr(exc, "status", None)) from exc

    @staticmethod
    async def _read_content(
        response: aiohttp.ClientResponse, max_bytes: int | None
    ) -> bytes:
        if max_bytes is None:
            return await response.read()
        body = bytearray()
        async for chunk in response.content.iter_chunked(65536):
            body.extend(chunk)
            if len(body) > max_bytes:
                raise HttpRequestError("HTTP response exceeds size limit")
        return bytes(body)

    @classmethod
    async def post(cls, url: str, body: dict, headers: dict | None = headers) -> bytes:
        try:
            async with (
                cls.session() as session,
                session.post(url, data=body, headers=headers) as response,
            ):
                return await response.content.read()
        except ClientConnectorError:
            raise HttpRequestError

    @classmethod
    async def delete(cls, url: str, headers: dict = headers) -> bytes:
        try:
            async with (
                cls.session() as session,
                session.delete(url, headers=headers) as response,
            ):
                return await response.content.read()
        except ClientError:
            raise HttpRequestError

    @classmethod
    async def get_json(cls, url: str, headers: dict = headers) -> dict:
        try:
            async with (
                cls.session() as session,
                session.get(url, headers=headers) as response,
            ):
                return await response.json()
        except ClientError:
            raise HttpRequestError

    @classmethod
    async def post_json(
        cls, url: str, json: dict, headers: dict | None = headers
    ) -> dict:
        try:
            async with (
                cls.session() as session,
                session.post(url, json=json, headers=headers) as response,
            ):
                response.raise_for_status()
                return await response.json()
        except (ClientError, TimeoutError) as exc:
            raise HttpRequestError(status=getattr(exc, "status", None)) from exc

    @classmethod
    async def get_status(cls, url: str, headers: dict | None = headers) -> int:
        try:
            async with (
                cls.session() as session,
                session.get(url, headers=headers) as response,
            ):
                return response.status
        except (ClientConnectorError, InvalidURL):
            raise HttpRequestError
