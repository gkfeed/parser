"""Owned loopback HTTP/Chromium resources. Run: make test-integration FILE=tests/browser."""

from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.chrome.service import Service


@dataclass(frozen=True)
class Page:
    body: str
    status: int = 200


@dataclass
class LocalSite:
    url: str = ""
    pages: dict[str, Page] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)

    def publish(self, body: str, *, status: int = 200, path: str = "/") -> str:
        self.pages[path] = Page(body, status)
        return self.url + path

    def handler(self) -> type[BaseHTTPRequestHandler]:
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                site.requests.append(self.path)
                page = site.pages.get(urlsplit(self.path).path, Page("Not found", 404))
                body = page.body.encode()
                self.send_response(page.status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args) -> None:
                return

        return Handler


@contextmanager
def local_site() -> Generator[LocalSite]:
    """Serve only on loopback, independently of the asyncio/browser thread."""
    site = LocalSite()
    with ThreadingHTTPServer(("127.0.0.1", 0), site.handler()) as server:
        site.url = f"http://127.0.0.1:{server.server_port}"
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
        thread.start()
        try:
            yield site
        finally:
            stop_server(server, thread)


def stop_server(server: ThreadingHTTPServer, thread: Thread) -> None:
    server.shutdown()
    thread.join(timeout=5)
    if thread.is_alive():
        raise RuntimeError("Local HTTP server did not stop")


class LocalChromium:
    """A factory of real browsers with fixture-owned fallback cleanup.

    SeleniumService quits each session. The surrounding ExitStack also cleans up
    browsers, services and temporary profiles if startup or a scenario fails.
    No Grid, production configuration, persistent profile or Selenium Manager.
    """

    def __init__(self, resources: ExitStack):
        self.resources = resources
        self.drivers: list[webdriver.Chrome] = []

    def __call__(self) -> webdriver.Chrome:
        chromium = which("chromium")
        chromedriver = which("chromedriver")
        if not chromium or not chromedriver:
            raise RuntimeError(
                "Browser integration tests require chromium and chromedriver"
            )
        profile = self.resources.enter_context(
            TemporaryDirectory(prefix="parser-test-")
        )
        options = webdriver.ChromeOptions()
        options.binary_location = chromium
        for flag in (
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-background-networking",
            "--no-proxy-server",
            "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
            f"--user-data-dir={profile}",
        ):
            options.add_argument(flag)
        service = Service(chromedriver)
        self.resources.callback(service.stop)
        driver = webdriver.Chrome(service=service, options=options)
        self.resources.callback(self.quit_if_running, driver)
        self.drivers.append(driver)
        return driver

    @staticmethod
    def quit_if_running(driver: webdriver.Chrome) -> None:
        service = driver.service
        if service is not None and service.process.poll() is None:
            driver.quit()

    def assert_released(self) -> None:
        """Check real process/socket state, without spying on quit()."""
        assert self.drivers, "The scenario must actually start Chromium"
        for driver in self.drivers:
            service = driver.service
            assert service is not None
            assert service.process.poll() is not None
            assert not service.is_connectable()
            lock = Path(driver.capabilities["chrome"]["userDataDir"]) / "SingletonLock"
            assert not lock.is_symlink()
