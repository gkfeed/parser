"""Local HTTP boundary shared by the deterministic parser contracts."""

import asyncio
from dataclasses import dataclass, field
from io import BytesIO

import pytest
from aiohttp import web
from PIL import Image


@dataclass
class ParserSite:
    url: str = ""
    pages: dict[str, web.Response] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)
    image_bodies: dict[str, bytes] = field(default_factory=dict)
    require_image_overlap: bool = False
    active_images: int = 0
    peak_images: int = 0
    overlapping_images: asyncio.Event = field(default_factory=asyncio.Event)

    def image(self, number: int) -> str:
        path = f"/images/{number}.png"
        output = BytesIO()
        Image.new("RGB", (2, 2), (number % 256, number // 256, 127)).save(
            output, format="PNG"
        )
        self.image_bodies[path] = output.getvalue()
        return self.url + path

    async def handle(self, request: web.Request) -> web.Response:
        self.requests.append(request.path_qs)
        if request.path in self.image_bodies:
            return await self.serve_image(request.path)
        if request.path not in self.pages:
            raise web.HTTPNotFound(text=f"No fixture for {request.path_qs}")
        return self.pages[request.path]

    async def serve_image(self, path: str) -> web.Response:
        self.active_images += 1
        self.peak_images = max(self.peak_images, self.active_images)
        if self.active_images >= 2:
            self.overlapping_images.set()
        try:
            if self.require_image_overlap:
                await asyncio.wait_for(self.overlapping_images.wait(), timeout=2)
            return web.Response(body=self.image_bodies[path], content_type="image/png")
        finally:
            self.active_images -= 1


@pytest.fixture
async def parser_site():
    site = ParserSite()
    app = web.Application()
    app.router.add_get("/{path:.*}", site.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    listener = web.TCPSite(runner, "127.0.0.1", 0)
    try:
        await listener.start()
        site.url = f"http://127.0.0.1:{runner.addresses[0][1]}"
        yield site
    finally:
        await runner.cleanup()
