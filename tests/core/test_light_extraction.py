import asyncio
from collections.abc import AsyncIterator

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.services.http import HttpService
from app.workers.youtube import extract_info


class ExtractionBoundary:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        app = web.Application()
        app.router.add_get("/video.mp4", self.video)
        app.router.add_get("/fast", self.fast)
        self.server = TestServer(app)

    async def video(self, request: web.Request) -> web.Response:
        self.started.set()
        await self.release.wait()
        # Generic extraction identifies a direct media URL from its headers.
        # No media is downloaded or decoded by extract_info(download=False).
        return web.Response(body=b"local media", content_type="video/mp4")

    async def fast(self, request: web.Request) -> web.Response:
        return web.Response(body=b"fast")

    def extract(self) -> asyncio.Task[dict]:
        return asyncio.create_task(
            extract_info(
                str(self.server.make_url("/video.mp4")),
                {"quiet": True, "socket_timeout": 2, "retries": 0},
                keys=["url", "ext"],
            )
        )


@pytest.fixture
async def source() -> AsyncIterator[ExtractionBoundary]:
    source = ExtractionBoundary()
    await source.server.start_server()
    try:
        yield source
    finally:
        source.release.set()
        await source.server.close()


async def test_real_extraction_leaves_event_loop_available(
    source: ExtractionBoundary,
) -> None:
    extraction = source.extract()
    try:
        await asyncio.wait_for(source.started.wait(), 5)
        assert await HttpService.get(str(source.server.make_url("/fast"))) == b"fast"
        assert not extraction.done()
    finally:
        source.release.set()
        info = await asyncio.wait_for(extraction, 5)
    assert info == {"url": str(source.server.make_url("/video.mp4")), "ext": "mp4"}


async def test_cancellation_waits_for_inflight_extraction(
    source: ExtractionBoundary,
) -> None:
    extraction = source.extract()
    try:
        await asyncio.wait_for(source.started.wait(), 5)
        extraction.cancel()
        assert await HttpService.get(str(source.server.make_url("/fast"))) == b"fast"
        assert not extraction.done()
    finally:
        source.release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(extraction, 5)


async def test_real_extraction_failure_raises(source: ExtractionBoundary) -> None:
    with pytest.raises(ValueError, match="yt-dlp extraction failed"):
        await extract_info(
            str(source.server.make_url("/missing")),
            {"quiet": True, "ignoreerrors": True, "socket_timeout": 2, "retries": 0},
        )
