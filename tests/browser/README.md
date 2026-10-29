# Local browser integration tests

Run `make test-integration FILE=tests/browser` after installing matching `chromium`
and `chromedriver` executables on PATH and running `uv sync --all-extras`.
Missing executables fail the scenarios instead of silently skipping coverage.
These tests do not need Redis, a broker, Docker or a Selenium Grid.

`resources.py` owns a loopback HTTP server and a factory of real headless Chromium
sessions. Each session has a temporary profile. An `ExitStack` closes sessions,
services and profiles even when startup, parsing or a scenario fails. The HTTP
server runs on its own thread because Selenium navigation blocks the test's
asyncio thread. Each fixture closes the browser before stopping the server.

Publish a page with `site.publish(html, status=200, path="/")`. It returns the
local URL. Subsequent publishes replace the response, so a scenario can retry the
same parser against a recovered source. Unregistered paths return HTTP 404.
`site.requests` records actual HTTP requests, including query strings.

Assign `parser.selenium_driver_factory = browser` to bind the local browser to
that parser instance. The service owns each acquired driver's lifetime; the
fixture provides fallback cleanup. Assign a `TemporaryCacheService` backed by
`MemoryStorage` to `parser.cache` to keep cache state local too. `source.py`
shows both assignments in a small diagnostic consumer. Its own actions decide
when to fail; the extension only records observations. `stories.py` configures the
real `InstagramStoriesFeed` with local instance dependencies and source pages.

The factory uses explicit local executable paths, disables proxies and background
networking, and blocks DNS resolution outside loopback. Cookie persistence is
never enabled by these sources. No production browser, profile, cookies, Grid,
container dependency or external worker is used. The generic Selenium service
still uses its configured container factory when no instance factory is supplied;
an explicit factory cannot fall back to an external worker.

All scenarios carry the `integration` marker and use real HTTP and Selenium.
`test_diagnostics.py` checks successful Items, unchanged consumer errors by type
and arguments, safe snapshot repr/SHA-256 logs and absent automatic classification.
`test_stories.py` exercises real Stories classification, retry, visibility, timeouts
and parser reuse. Successful loading and pagination use its public `get_html`
operation so media upload and hashing stay outside these browser scenarios.
`test_lifetime.py` checks cancellation, closed driver processes/sockets, profile
removal and HTTP server shutdown. Existing repository-wide autouse fixtures remain
unchanged; these scenarios add no monkeypatches or container replacements.

The local service accepts an optional driver factory, with the existing container
factory as its default. Local arguments use shallow field extraction because
`dataclasses.asdict` deep-copies a bound callback's parser, including its factory.
An owned factory contains live drivers and cleanup callbacks after the first run;
copying those fails on thread locks and breaks reuse. This narrow boundary keeps
instance dependencies usable without changing the global injection decorator or
any Stories policy. Scenarios do not compare exception identity.
