import json as json_module
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPMethod
from types import MappingProxyType
from typing import Any, Self

import aiohttp

DEFAULT_HEADERS: Mapping[str, str] = MappingProxyType(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/106.0.0.0 Safari/537.36"
        )
    }
)
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)


@dataclass(frozen=True)
class HttpResponse[ResponseData]:
    status: int
    data: ResponseData


class HttpRequestError(Exception):
    """Base error raised by the application HTTP client."""

    def __init__(self, method: str, url: str, message: str) -> None:
        self.method = method
        self.url = url
        super().__init__(f"{method} {url}: {message}")


class HttpTransportError(HttpRequestError):
    """The request failed before a complete HTTP response was received."""


class HttpStatusError(HttpRequestError):
    """The server returned an unsuccessful HTTP status."""

    def __init__(self, method: str, url: str, status: int, body: bytes) -> None:
        self.status = status
        self.body = body[:512]
        preview = self.body.decode("utf-8", errors="replace")
        super().__init__(method, url, f"HTTP {status}: {preview}")


class HttpDecodeError(HttpRequestError):
    """The response body could not be decoded as JSON."""


class HttpClient:
    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> Self:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def request_bytes(
        self,
        method: HTTPMethod,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        raise_for_status: bool = True,
    ) -> HttpResponse[bytes]:
        session = self._require_session()
        request_headers = {**DEFAULT_HEADERS, **(headers or {})}
        normalized_method = method.upper()

        try:
            async with session.request(
                normalized_method,
                url,
                data=data,
                json=json,
                headers=request_headers,
                timeout=timeout or DEFAULT_TIMEOUT,
            ) as response:
                body = await response.read()
                if raise_for_status and response.status >= 400:
                    raise HttpStatusError(
                        normalized_method,
                        str(response.url),
                        response.status,
                        body,
                    )
                return HttpResponse(status=response.status, data=body)
        except (aiohttp.ClientError, TimeoutError) as error:
            raise HttpTransportError(
                normalized_method,
                url,
                str(error) or error.__class__.__name__,
            ) from error

    async def request_json(
        self,
        method: HTTPMethod,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
        raise_for_status: bool = True,
    ) -> HttpResponse[Any]:
        response = await self.request_bytes(
            method,
            url,
            data=data,
            json=json,
            headers=headers,
            timeout=timeout,
            raise_for_status=raise_for_status,
        )
        try:
            decoded = json_module.loads(response.data)
        except (UnicodeDecodeError, json_module.JSONDecodeError) as error:
            raise HttpDecodeError(
                method.upper(), url, "invalid JSON response"
            ) from error
        return HttpResponse(status=response.status, data=decoded)

    def _require_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise RuntimeError(
                "HttpClient must be used inside an async context manager"
            )
        return self._session
