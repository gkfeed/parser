"""Isolated browser experiment; run from the repository root with PYTHONPATH=."""

import argparse
import asyncio
import importlib
import json
import os
import platform
import signal
import sys
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import cached_property
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from typing import Any

from aiohttp import web

FEEDS = {
    "hltv": "https://www.hltv.org/team/7020/spirit",
    "rezka": "https://hdrezka.me/films/action/64700-major-grom-game-the-2024.html",
}
HLTV_READY = (
    "//h2[contains(@class, 'standard-headline') and "
    "starts-with(normalize-space(.), 'Upcoming matches for')]"
)
HLTV_FIXTURE = """<!doctype html><title>HLTV fixture</title><body>
<script>setTimeout(() => {document.body.innerHTML = `
<h2 hidden class="standard-headline">Upcoming matches for Spirit</h2>
<table class="table-container match-table"><tr class="team-row">
<td class="team-center-cell"><div class="team-flex"><b class="team-name">Spirit</b></div>
<div class="team-flex"><b class="team-name">Example</b></div></td>
<td class="matchpage-button-cell"><a href="/matches/123/spike">Match</a></td>
<td class="date-cell"><span data-unix="1792666800000">Date</span></td>
</tr></table>`}, 200);</script></body>"""
REZKA_FIXTURE = """<!doctype html><title>Rezka fixture</title>
<input id="post_id" value="64700"><div class="b-post__title"><h1>Spike film</h1></div>
<div class="b-post__lastepisodeout"><h2>Available</h2></div>"""


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["selenium", "camoufox"], required=True)
    parser.add_argument("--mode", choices=["live", "fixture"], default="fixture")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--remote", help="Camoufox Playwright WebSocket endpoint")
    parser.add_argument("--grid", help="Isolated Selenium Grid URL, live mode only")
    parser.add_argument(
        "--server-pid", type=int, help="Optional local server RSS sampling"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", choices=list(FEEDS), help=argparse.SUPPRESS)
    parser.add_argument("--target", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.runs < 1 or args.concurrency < 1:
        parser.error("runs and concurrency must be positive")
    if args.engine == "camoufox" and not (args.binary or args.remote):
        parser.error("Camoufox requires a pinned --binary or --remote endpoint")
    if args.engine == "selenium" and args.remote:
        parser.error("--remote is a Playwright endpoint, not a Selenium endpoint")
    if args.grid and (args.engine != "selenium" or args.mode != "live"):
        parser.error("--grid requires --engine selenium --mode live")
    return args


def snapshot_parser(name: str, html: bytes):
    from app.parsers.hltv import HltvFeed
    from app.parsers.rezka import RezkaFeed
    from app.serializers.feed import Feed
    from app.services.rezka import RezkaClient

    class SnapshotHltv(HltvFeed):
        async def get_html(self, url: str) -> bytes:
            self._validate_html(url, html)
            return html

    class SnapshotRezka(RezkaFeed):
        @cached_property
        def _client(self) -> RezkaClient:
            return RezkaClient(self.get_html)

        async def get_html(self, url: str, *, attempts: int = 3) -> bytes:
            if url != self.feed.url:
                raise ValueError(f"Snapshot cannot supply another page: {url}")
            self._validate_html(url, html)
            return html

    cls = {"hltv": SnapshotHltv, "rezka": SnapshotRezka}[name]
    return cls(Feed(id=1, type=name, title=name, url=FEEDS[name]), {})


async def parse_snapshot(name: str, html: bytes, fixture: bool) -> list[dict]:
    parser = snapshot_parser(name, html)
    items = await parser.apply_hashes(await parser.items)
    if not items:
        raise ValueError("Selected feed must produce at least one item")
    if fixture:
        expected_title = "Spirit vs Example" if name == "hltv" else "Available"
        assert len(items) == 1 and items[0].title == expected_title, items
        expected_link = "https://www.hltv.org/matches/123/spike"
        if name == "rezka":
            expected_link = FEEDS[name]
        assert items[0].link == expected_link, items
        assert items[0].hash, items
    return [item.model_dump(mode="json") for item in items]


async def selenium_html(args) -> tuple[bytes, str]:
    import app.configs  # noqa: F401 - installs the existing driver factory
    from app.services.selenium import SeleniumGetHtmlArgs, SeleniumService

    if args.grid:
        configure_grid_driver()
    parser = snapshot_parser(args.worker, b"")
    browser_version = "unknown"

    def actions(driver):
        nonlocal browser_version
        browser_version = driver.capabilities["browserVersion"]
        try:
            # Exercise the actual production WebDriver callback, including HLTV wait.
            parser.make_actions(driver)
        except BaseException as exc:
            save_failed_selenium_page(driver, args.output / "page.html", exc)
            raise
        (args.output / "page.html").write_text(driver.page_source)

    html = await SeleniumService.get_html(
        SeleniumGetHtmlArgs(
            url=args.target,
            should_delete_cookies=False,
            should_load_cookies=False,
            should_save_cookies=False,
            make_actions_function=actions,
            selenium_wait_timeout_seconds=5 if args.worker == "rezka" else 0,
            page_load_timeout_seconds=30,
            blocked_url_patterns=(),
        ),
        fallback_to_external_selenium=False,
    )
    return html.encode(), browser_version


def configure_grid_driver() -> None:
    from dataclasses import replace

    from app.configs.selenium import _get_docker_driver
    from app.services.container import Container

    # Per-process dependency injection, using the production Grid driver factory.
    data = replace(Container.get_data(), selenium_web_driver=_get_docker_driver)
    Container.setup(data)


def save_failed_selenium_page(driver, path: Path, original: BaseException) -> None:
    from selenium.common.exceptions import WebDriverException

    try:
        path.write_text(driver.page_source)
    except (WebDriverException, OSError) as exc:
        original.add_note(f"Could not capture failed page: {exc}")


def launch_options(args) -> dict[str, Any]:
    addons = importlib.import_module("camoufox.addons")
    return {
        "headless": True,
        "executable_path": str(args.binary.resolve()),
        "os": "linux",
        "exclude_addons": list(addons.DefaultAddons),
        "timeout": 30_000,
    }


@asynccontextmanager
async def camoufox_browser(args):
    if not args.remote:
        api = importlib.import_module("camoufox.async_api")
        async with api.AsyncCamoufox(**launch_options(args)) as browser:
            yield browser
        return
    api = importlib.import_module("playwright.async_api")
    async with api.async_playwright() as playwright:
        browser = await playwright.firefox.connect(args.remote, timeout=30_000)
        try:
            yield browser
        finally:
            await browser.close()


async def cookie_and_timeout_probe(browser, target: str, output: Path) -> None:
    """Local HTTP boundary check, never uses or writes production cookie files."""
    origin = target.rsplit("/", 1)[0]
    async with await browser.new_context() as context:
        await context.add_cookies([{"name": "loaded", "value": "yes", "url": origin}])
        page = await context.new_page()
        await page.goto(origin + "/cookie", timeout=5_000)
        assert await page.locator("#loaded").inner_text() == "yes"
        state = output / "storage-state.json"
        state.touch(mode=0o600)
        await context.storage_state(path=state)
    async with await browser.new_context(storage_state=str(state)) as context:
        restored = {
            cookie["name"]: cookie["value"] for cookie in await context.cookies()
        }
        assert restored == {"loaded": "yes", "persisted": "yes"}, restored
        page = await context.new_page()
        await page.goto(origin + "/cookie", timeout=5_000)
        assert "persisted=yes" in await page.evaluate("document.cookie")
    async with await browser.new_context() as context:
        assert await context.cookies() == [], "Cookies leaked across contexts"
        page = await context.new_page()
        api = importlib.import_module("playwright.async_api")
        try:
            await page.goto(origin + "/slow", timeout=100)
        except api.TimeoutError:
            return
        raise AssertionError("Navigation deadline did not raise TimeoutError")


async def camoufox_html(args) -> tuple[bytes, str]:
    async with camoufox_browser(args) as browser:
        html = await camoufox_page(browser, args)
        if args.mode == "fixture":
            await cookie_and_timeout_probe(browser, args.target, args.output)
        return html, browser.version


async def camoufox_page(browser, args) -> bytes:
    async with await browser.new_context() as context:
        page = await context.new_page()
        return await capture_page(page, args)


async def capture_page(page, args) -> bytes:
    path = args.output / "page.html"
    try:
        await navigate(page, args)
    except BaseException as exc:
        await save_failed_page(page, path, exc)
        raise
    html = await page.content()
    path.write_text(html)
    return html.encode()


async def save_failed_page(page, path: Path, original: BaseException) -> None:
    api = importlib.import_module("playwright.async_api")
    try:
        path.write_text(await page.content())
    except (api.Error, OSError) as exc:
        original.add_note(f"Could not capture failed page: {exc}")


async def navigate(page, args) -> None:
    response = await page.goto(args.target, wait_until="load", timeout=30_000)
    if response is None or not response.ok:
        status = response.status if response else "no response"
        raise ValueError(f"Navigation failed: HTTP {status}")
    if args.worker == "hltv":
        # Port the required callback to Playwright; WebDriver is incompatible.
        await page.locator("xpath=" + HLTV_READY).wait_for(
            state="attached", timeout=30_000
        )
        return
    await asyncio.sleep(5)


async def worker(args) -> None:
    args.output.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"success": False}
    started = time.monotonic()
    try:
        fetch = selenium_html if args.engine == "selenium" else camoufox_html
        html, browser_version = await fetch(args)
        items = await parse_snapshot(args.worker, html, args.mode == "fixture")
        if args.mode == "fixture":
            await reject_malformed_snapshot(args.worker)
        result.update(
            browser_version=browser_version,
            html_sha256=sha256(html).hexdigest(),
            html_bytes=len(html),
            items=items,
            success=True,
        )
    except Exception as exc:
        # A benchmark records failures explicitly, then exits unsuccessfully.
        result.update(error_type=type(exc).__name__, error=str(exc)[:2000])
        raise
    finally:
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (args.output / "result.json").write_text(json.dumps(result, indent=2))


async def reject_malformed_snapshot(name: str) -> None:
    from app.extensions.parsers.exceptions import FeedUnavailable

    try:
        await snapshot_parser(name, b"<html><title>Broken page</title></html>").items
    except (FeedUnavailable, ValueError):
        return
    raise AssertionError("Malformed page was accepted as an empty feed")


async def fixture_page(request: web.Request) -> web.Response:
    if request.path == "/slow":
        await asyncio.sleep(2)
    if request.path == "/hltv":
        return web.Response(text=HLTV_FIXTURE, content_type="text/html")
    if request.path == "/rezka":
        return web.Response(text=REZKA_FIXTURE, content_type="text/html")
    if request.path == "/cookie":
        response = web.Response(
            text=f'<p id="loaded">{request.cookies.get("loaded", "missing")}</p>',
            content_type="text/html",
        )
        response.set_cookie("persisted", "yes")
        return response
    return web.Response(text="<!doctype html><title>Empty fixture</title>")


@asynccontextmanager
async def fixture_server():
    app = web.Application()
    app.router.add_get("/{path:.*}", fixture_page)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        address = runner.addresses[0]
        yield f"http://127.0.0.1:{address[1]}"
    finally:
        await runner.cleanup()


def tree_rss(pid: int) -> int:
    psutil = importlib.import_module("psutil")
    try:
        root = psutil.Process(pid)
        processes = [root, *root.children(recursive=True)]
    except psutil.NoSuchProcess:
        return 0
    rss = 0
    for process in processes:
        try:
            rss += process.memory_info().rss
        except psutil.NoSuchProcess:
            continue
    return rss


async def measure(process) -> int:
    peak = 0
    while process.returncode is None:
        peak = max(peak, tree_rss(process.pid))
        await asyncio.sleep(0.1)
    return peak


async def bounded_wait(process) -> None:
    try:
        await asyncio.wait_for(process.wait(), timeout=100)
    except TimeoutError:
        await stop_process(process)
    except asyncio.CancelledError:
        await stop_process(process)
        raise


async def stop_process(process) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        os.killpg(process.pid, signal.SIGKILL)
        await process.wait()


async def sample_server(pid: int, done: asyncio.Event) -> int:
    peak = 0
    while not done.is_set():
        peak = max(peak, tree_rss(pid))
        await asyncio.sleep(0.1)
    return peak


async def attempt(args, name: str, index: int, origin: str, limit) -> dict:
    async with limit:
        return await run_attempt(args, name, index, origin)


async def run_attempt(args, name: str, index: int, origin: str) -> dict:
    directory = args.output / f"{name}-{index}"
    directory.mkdir(parents=True, exist_ok=False)
    command = [
        sys.executable,
        __file__,
        "--engine",
        args.engine,
        "--mode",
        args.mode,
        "--worker",
        name,
        "--target",
        f"{origin}/{name}" if origin else FEEDS[name],
        "--output",
        str(directory),
    ]
    if args.binary:
        command.extend(["--binary", str(args.binary)])
    if args.remote:
        command.extend(["--remote", args.remote])
    if args.grid:
        command.extend(["--grid", args.grid])
    # No DB/Redis/broker calls are needed. Never read production credentials.
    env = dict(
        os.environ,
        DB_URL="postgresql+asyncpg://spike:spike@localhost/spike",
        TWITCH_CLIENT_ID="spike",
        TWITCH_CLIENT_SECRET="spike",
        REDIS_HOST="localhost",
    )
    if args.grid:
        env["SELENIUM_DOCKER_URL"] = args.grid
    with (directory / "worker.log").open("w") as log:
        process = await asyncio.create_subprocess_exec(
            *command, env=env, stdout=log, stderr=log, start_new_session=True
        )
        sampler = asyncio.create_task(measure(process))
        await bounded_wait(process)
        peak = await sampler
    result_path = directory / "result.json"
    result: dict[str, Any]
    if result_path.exists():
        result = json.loads(result_path.read_text())
    else:
        result = {"success": False, "error_type": "WorkerTerminated"}
    result.update(
        feed=name,
        run=index,
        exit_code=process.returncode,
        peak_process_tree_rss_mib=round(peak / 1024**2, 1),
    )
    if process.returncode != 0:
        result["success"] = False
    print(json.dumps({k: v for k, v in result.items() if k != "items"}), flush=True)
    return result


async def main(args) -> bool:
    if args.worker:
        await worker(args)
        return True
    args.output.mkdir(parents=True, exist_ok=False)
    limit = asyncio.Semaphore(args.concurrency)
    done = asyncio.Event()
    server_sampler = None
    if args.server_pid:
        if not (args.remote or args.grid) or tree_rss(args.server_pid) == 0:
            raise ValueError("--server-pid requires --remote/--grid and a local server")
        server_sampler = asyncio.create_task(sample_server(args.server_pid, done))
    async with fixture_server() as origin:
        target = origin if args.mode == "fixture" else ""
        jobs = [
            attempt(args, name, index, target, limit)
            for index in range(args.runs)
            for name in FEEDS
        ]
        results = await asyncio.gather(*jobs)
    done.set()
    server_peak = await server_sampler if server_sampler else None
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "engine": args.engine,
        "mode": args.mode,
        "concurrency": args.concurrency,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "packages": {
            name: version(name)
            for name in ["camoufox", "playwright", "selenium", "psutil"]
        },
        "remote": bool(args.remote),
        "grid": bool(args.grid),
        "shared_server_peak_rss_mib": round(server_peak / 1024**2, 1)
        if server_peak
        else None,
        "results": results,
    }
    (args.output / "results.json").write_text(json.dumps(report, indent=2))
    return all(result["success"] for result in results)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main(parse_args())) else 1)
