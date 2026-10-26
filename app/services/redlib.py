import json
import ssl
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from socket import gaierror
from urllib.parse import urlsplit

import structlog
from aiohttp import (
    ClientConnectionError,
    ClientConnectorDNSError,
    ClientPayloadError,
    ClientSSLError,
)

from app.extensions.parsers.exceptions import FeedUnavailable
from app.services.http import HttpRequestError, HttpService
from app.services.url_ranker import URLRanker
from app.utils.logging import url_log_fields

logger = structlog.get_logger(__name__)


class InvalidRedlibPage(ValueError):
    """A mirror returned neither posts nor a confirmed empty listing."""


class RedlibClient:
    _instances_url = "https://raw.githubusercontent.com/redlib-org/redlib-instances/main/instances.json"
    _default_url_ranker = URLRanker(data_file="data/reddit_url_ranks.json")

    def __init__(
        self,
        fetch: Callable[[str], Awaitable[bytes]],
        *,
        fetch_instances: Callable[[str], Awaitable[bytes]] = HttpService.get,
        url_ranker: URLRanker | None = None,
    ) -> None:
        # The caller validates source pages before returning or caching them.
        self._fetch = fetch
        self._fetch_instances = fetch_instances
        self._url_ranker = (
            url_ranker if url_ranker is not None else self._default_url_ranker
        )
        self._base_urls_cache: list[str] | None = None

    async def _get_base_urls(self) -> list[str]:
        if self._base_urls_cache is not None:
            return self._base_urls_cache

        response = await self._fetch_instances(self._instances_url)
        try:
            instances_data = json.loads(response)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError(
                "Redlib instance directory returned invalid JSON"
            ) from error
        instances = (
            instances_data.get("instances")
            if isinstance(instances_data, Mapping)
            else None
        )
        if not isinstance(instances, list):
            raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                "Redlib instance directory must contain an instances list"
            )

        all_urls: list[str] = []
        for instance in instances:
            if not isinstance(instance, Mapping):
                raise ValueError(  # noqa: TRY004 - malformed API data is a value error
                    "Redlib instance directory contains an invalid instance"
                )
            # The directory also lists onion-only instances without a clearnet URL.
            if "url" not in instance:
                continue
            all_urls.append(self._get_instance_url(instance["url"]))
        # Cache the directory, not the cooldown/ranking snapshot.
        self._base_urls_cache = all_urls
        return self._base_urls_cache

    @staticmethod
    def _get_instance_url(url: object) -> str:
        if not isinstance(url, str) or not url:
            raise ValueError("Redlib instance is missing a valid URL")
        parsed_url = urlsplit(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError(f"Invalid Redlib instance URL: {url}")
        return url

    async def get_page_html(self, page_url: str) -> bytes:
        all_urls = await self._get_base_urls()
        base_urls = self._url_ranker.get_ranked_urls(all_urls)
        failures: Counter[str] = Counter()
        last_error: FeedUnavailable | InvalidRedlibPage | HttpRequestError | None = None
        path = "/".join(page_url.split("/")[3:])

        for base_url in base_urls:
            try:
                html = await self._fetch(base_url.rstrip("/") + "/" + path)
            except (FeedUnavailable, InvalidRedlibPage, HttpRequestError) as error:
                last_error = error
                self._url_ranker.demote_url(base_url)
                reason = self._failure_reason(error)
                failures[reason] += 1
                http_error = self._http_error(error)
                logger.warning(
                    "reddit_mirror_failed",
                    **url_log_fields(base_url, field="mirror"),
                    reason=reason,
                    attempt=sum(failures.values()),
                    error_type=type(error).__name__,
                    cause_type=type(http_error.__cause__).__name__
                    if http_error is not None and http_error.__cause__ is not None
                    else None,
                    http_status=http_error.status if http_error is not None else None,
                )
                continue

            self._url_ranker.promote_url(base_url)
            return html

        reason = "mirrors_on_cooldown" if all_urls else "no_mirrors_configured"
        if last_error is not None:
            reason = self._failure_reason(last_error)
        cooldowns = [
            retry_at
            for url in all_urls
            if (retry_at := self._url_ranker.get_cooldown_until(url)) is not None
        ]
        retry_at = min(cooldowns) if cooldowns else None
        logger.warning(
            "reddit_mirrors_exhausted",
            reason=reason,
            mirrors_configured=len(all_urls),
            mirrors_available=len(base_urls),
            mirrors_cooling_down=len(all_urls) - len(base_urls),
            mirrors_attempted=sum(failures.values()),
            failure_counts=dict(failures),
            retry_at=retry_at.isoformat() if retry_at else None,
        )
        raise FeedUnavailable(
            page_url, f"reddit_mirrors_exhausted:{reason}", retry_at
        ) from last_error

    @classmethod
    def _failure_reason(
        cls,
        error: FeedUnavailable | InvalidRedlibPage | HttpRequestError,
    ) -> str:
        http_error = cls._http_error(error)
        if http_error is not None:
            return cls._http_failure_reason(http_error)
        if isinstance(error, FeedUnavailable):
            return error.reason
        return "invalid_page"

    @staticmethod
    def _http_error(error: Exception) -> HttpRequestError | None:
        # HttpParserExtension wraps the service error in FeedUnavailable.
        if isinstance(error, HttpRequestError):
            return error
        if isinstance(error.__cause__, HttpRequestError):
            return error.__cause__
        return None

    @staticmethod
    def _http_failure_reason(error: HttpRequestError) -> str:
        if error.status is not None:
            return "http_status"
        cause = error.__cause__
        if isinstance(cause, (ClientSSLError, ssl.SSLError)):
            return "tls_error"
        if isinstance(cause, (ClientConnectorDNSError, gaierror)):
            return "dns_error"
        if isinstance(cause, TimeoutError):
            return "timeout"
        if isinstance(cause, ClientConnectionError):
            return "connection_error"
        if isinstance(cause, ClientPayloadError):
            return "response_payload_error"
        return "http_request_failed"
