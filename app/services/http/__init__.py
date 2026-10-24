from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import aiohttp
from aiohttp.client_exceptions import ClientError

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
    @asynccontextmanager
    async def _request(
        cls,
        method: str,
        url: str,
        *,
        headers: dict | None,
        data: dict | None = None,
        json: dict | None = None,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[aiohttp.ClientResponse]:
        try:
            async with (
                cls.session() as session,
                session.request(
                    method,
                    url,
                    headers=headers,
                    data=data,
                    json=json,
                    raise_for_status=raise_for_status,
                ) as response,
            ):
                yield response
        except (ClientError, TimeoutError) as exc:
            raise HttpRequestError(status=getattr(exc, "status", None)) from exc

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
        async with cls._request(
            "GET", url, headers=headers, raise_for_status=False
        ) as response:
            content = await cls._read_content(response, max_bytes)
            return HttpResponse(
                response.status,
                content,
                {key.lower(): value for key, value in response.headers.items()},
            )

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
        async with cls._request("POST", url, headers=headers, data=body) as response:
            return await response.read()

    @classmethod
    async def delete(cls, url: str, headers: dict = headers) -> bytes:
        async with cls._request("DELETE", url, headers=headers) as response:
            return await response.read()

    @classmethod
    async def get_json(
        cls,
        url: str,
        headers: dict = headers,
        *,
        content_type: str | None = "application/json",
        expected_status: int | None = None,
    ) -> dict:
        async with cls._request("GET", url, headers=headers) as response:
            if expected_status is not None and response.status != expected_status:
                raise HttpRequestError(
                    f"Unexpected HTTP status {response.status}", status=response.status
                )
            return await response.json(content_type=content_type)

    @classmethod
    async def post_json(
        cls, url: str, json: dict, headers: dict | None = headers
    ) -> dict:
        async with cls._request("POST", url, headers=headers, json=json) as response:
            return await response.json()

    @classmethod
    async def get_status(cls, url: str, headers: dict | None = headers) -> int:
        async with cls._request(
            "GET", url, headers=headers, raise_for_status=False
        ) as response:
            return response.status
