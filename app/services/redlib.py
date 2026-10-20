import json
from collections.abc import Awaitable, Callable, Mapping
from urllib.parse import urlsplit

import structlog

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
        if self._base_urls_cache:
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
        self._base_urls_cache = self._url_ranker.get_ranked_urls(all_urls)
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
        base_urls = await self._get_base_urls()
        last_error: FeedUnavailable | InvalidRedlibPage | HttpRequestError | None = None
        path = "/".join(page_url.split("/")[3:])

        for base_url in base_urls:
            try:
                html = await self._fetch(base_url.rstrip("/") + "/" + path)
            except (FeedUnavailable, InvalidRedlibPage, HttpRequestError) as error:
                last_error = error
                self._url_ranker.demote_url(base_url)
                logger.warning(
                    "reddit_mirror_failed",
                    **url_log_fields(base_url, field="mirror"),
                    reason=self._failure_reason(error),
                )
                continue

            self._url_ranker.promote_url(base_url)
            return html

        reason = "no_mirrors_available"
        if last_error is not None:
            reason = self._failure_reason(last_error)
        retry_at = (
            last_error.retry_at if isinstance(last_error, FeedUnavailable) else None
        )
        raise FeedUnavailable(
            page_url, f"reddit_mirrors_exhausted:{reason}", retry_at
        ) from last_error

    @staticmethod
    def _failure_reason(
        error: FeedUnavailable | InvalidRedlibPage | HttpRequestError,
    ) -> str:
        if isinstance(error, FeedUnavailable):
            return error.reason
        if isinstance(error, HttpRequestError):
            return "http_request_failed"
        return "invalid_page"
