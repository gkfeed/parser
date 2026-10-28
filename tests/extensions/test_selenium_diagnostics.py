import json
import shutil
from dataclasses import replace
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import override

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from structlog.testing import capture_logs

from app.extensions.parsers.exceptions import FeedUnavailable
from app.extensions.parsers.selenium_diagnostics import SeleniumDiagnosticsExtension
from app.serializers.feed import Feed
from app.services.container import Container

pytestmark = pytest.mark.integration


class DiagnosticFeed(SeleniumDiagnosticsExtension):
    _selenium_wait_time = 0
    _results_wait_time = 0
    _service_url = ""

    @override
    async def _parse_items(self):
        await self.get_html(self._service_url)
        # The ready marker confirms that this synthetic source loaded.
        return []

    @override
    def _make_actions(self):
        self._wait_for(
            "catalog_ready", EC.presence_of_element_located((By.ID, "ready"))
        )


class CatalogFeed(DiagnosticFeed):
    _diagnostic_event = "catalog_unavailable"

    @override
    def _make_actions(self):
        errors = self.driver.find_elements(By.ID, "error")
        if errors:
            self._check_error(errors[0], "catalog_response")
        super()._make_actions()

    @override
    def _browser_context(self):
        return self.driver.execute_script(
            """
            const entries = [...document.querySelectorAll('.entry')];
            return {
                document_status: performance.getEntriesByType('navigation')[0]?.responseStatus || null,
                entries: entries.length,
                visible_entries: entries.filter(e =>
                    e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})).length,
                page_message: document.querySelector('#catalog') ? '' :
                    document.title + ' ' + (document.body?.innerText || '')
            };
            """
        )

    @classmethod
    @override
    def _classify_browser_error(cls, message):
        if message == "Catalog closed":
            return "catalog_closed"
        return super()._classify_browser_error(message)


@pytest.fixture
def local_browser_source():
    chromium = shutil.which("chromium")
    chromedriver = shutil.which("chromedriver")
    if not chromium or not chromedriver:
        pytest.skip()
    response: dict = {"status": 200, "body": ""}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(response["status"])
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(response["body"].encode())

        def log_message(self, format: str, *args):
            pass

    def new_driver():
        options = webdriver.ChromeOptions()
        options.binary_location = chromium
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        return webdriver.Chrome(service=Service(chromedriver), options=options)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    original = Container.get_data()
    Container.setup(replace(original, selenium_web_driver=new_driver))
    thread.start()
    try:
        yield response, f"http://127.0.0.1:{server.server_port}/"
    finally:
        Container.setup(original)
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    ("feed_type", "status", "body", "reason"),
    [
        (
            DiagnosticFeed,
            503,
            "<title>Service unavailable</title>",
            "upstream_http_error",
        ),
        (
            DiagnosticFeed,
            403,
            "<title>Verify you are human</title>",
            "challenge_required",
        ),
        (
            DiagnosticFeed,
            200,
            "No stories for the last 24 hours",
            "catalog_ready_timeout",
        ),
        (CatalogFeed, 200, '<div id="error">Error: 429</div>', "rate_limited"),
        (CatalogFeed, 200, '<div id="error">Catalog closed</div>', "catalog_closed"),
        (
            CatalogFeed,
            200,
            '<div id="error">Failed token=SECRET_MARKER</div>',
            "upstream_error",
        ),
        (CatalogFeed, 200, "", "catalog_ready_timeout"),
        (CatalogFeed, 200, '<div id="ready"></div>', None),
    ],
)
async def test_configurable_browser_diagnostics(
    local_browser_source, feed_type, status, body, reason
):
    response, url = local_browser_source
    if feed_type is CatalogFeed:
        body = (
            '<div id="catalog"><i class="entry"></i><i class="entry" hidden></i>'
            + body
            + "</div>"
        )
    response.update(status=status, body=body)
    parser = feed_type(Feed(id=1, title="Local", type="test", url=url), {})
    parser._service_url = url

    with capture_logs() as logs:
        await check_source_outcome(parser, reason)

    if reason is None:
        assert logs == []
        return
    assert len(logs) == 1
    event = logs[0]
    assert event["reason"] == reason
    assert event["document_status"] == status
    assert event["stage"] in ("catalog_response", "catalog_ready")
    assert "SECRET_MARKER" not in json.dumps(logs)
    assert "source_message" not in event
    assert "page_message" not in event
    if feed_type is CatalogFeed:
        assert event["event"] == "catalog_unavailable"
        assert event["entries"] == 2
        assert event["visible_entries"] == 1
        return
    assert event["event"] == "browser_source_unavailable"
    assert "entries" not in event


async def check_source_outcome(parser, reason):
    if reason is None:
        assert await parser.items == []
        return
    with pytest.raises(FeedUnavailable) as raised:
        await parser.items
    assert raised.value.reason == reason
    assert raised.value.url == parser.feed.url
    assert raised.value.retry_at is None
    if reason.endswith("_timeout"):
        assert raised.value.__cause__ is not None


@pytest.mark.parametrize("reason", [None, "catalog_closed", "catalog_ready_timeout"])
async def test_browser_actions_release_driver_for_reuse(local_browser_source, reason):
    response, url = local_browser_source
    parser = CatalogFeed(Feed(id=1, title="Local", type="test", url=url), {})
    parser._service_url = url
    parser._http_response_storage_time = timedelta(0)
    body = {
        None: '<div id="ready"></div>',
        "catalog_closed": '<div id="error">Catalog closed</div>',
        "catalog_ready_timeout": "",
    }[reason]
    response.update(status=200, body=f'<div id="catalog">{body}</div>')

    with capture_logs():
        await check_source_outcome(parser, reason)
    with pytest.raises(RuntimeError, match="Browser actions are not active"):
        _ = parser.driver

    response.update(body='<div id="catalog"><div id="ready"></div></div>')
    with capture_logs() as logs:
        assert await parser.items == []
    assert logs == []
    with pytest.raises(RuntimeError, match="Browser actions are not active"):
        _ = parser.driver
