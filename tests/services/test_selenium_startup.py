import asyncio
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread, Timer
from time import monotonic

import pytest
import requests

from app.run.worker_heavy import prepare_grid
from app.utils.selenium import cleanup_grid

pytestmark = pytest.mark.integration


class GridEndpoint:
    def __init__(self):
        self.payload = {"value": {"ready": True, "nodes": [{"slots": []}]}}
        self.status = 200
        self.delay = 0.0
        self.requested = Event()
        self.requests = 0
        self.deleted = []
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                assert self.path == "/status"
                endpoint.requests += 1
                endpoint.requested.set()
                Event().wait(endpoint.delay)
                body = json.dumps(endpoint.payload).encode()
                self.send_response(endpoint.status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except BrokenPipeError:
                    # A deadline or cancellation can close the client first.
                    pass

            def do_DELETE(self):
                endpoint.deleted.append(self.path)
                endpoint.payload["value"]["nodes"] = [{"slots": []}]
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format, *_args):
                pass

        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), Handler, bind_and_activate=False
        )
        # Reserve the port without listening, so TCP really refuses connections.
        self.server.server_bind()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = None

    def start(self):
        self.server.server_activate()
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        if self.thread is not None:
            self.server.shutdown()
            self.thread.join(timeout=5)
        self.server.server_close()


@contextmanager
def grid_endpoint(*, listening=True):
    endpoint = GridEndpoint()
    if listening:
        endpoint.start()
    try:
        yield endpoint
    finally:
        endpoint.close()


def test_refused_startup_waits_until_grid_listens(capsys):
    with grid_endpoint(listening=False) as grid:
        timer = Timer(0.3, grid.start)
        timer.start()
        try:
            cleanup_grid(grid.url, timeout_seconds=3)
        finally:
            timer.join(timeout=5)
        assert grid.requests == 1
        assert grid.deleted == []
    logs = capsys.readouterr().out
    assert "connection_refused" in logs
    assert "selenium_grid_startup_ready" in logs


def test_grid_must_report_ready_before_startup_succeeds(capsys):
    with grid_endpoint() as grid:
        grid.payload["value"]["ready"] = False
        timer = Timer(0.3, lambda: grid.payload["value"].update(ready=True))
        timer.start()
        try:
            cleanup_grid(grid.url, timeout_seconds=3)
        finally:
            timer.join(timeout=5)
        assert grid.requests >= 2
    assert "not_ready" in capsys.readouterr().out


def test_unreachable_grid_fails_with_bounded_wait(capsys):
    with grid_endpoint(listening=False) as grid:
        started = monotonic()
        with pytest.raises(TimeoutError) as raised:
            cleanup_grid(grid.url, timeout_seconds=0.2)
        assert monotonic() - started < 2
        assert isinstance(raised.value.__cause__, requests.ConnectionError)
    logs = capsys.readouterr().out
    assert "connection_refused" in logs
    assert "deadline_exceeded" in logs
    assert "selenium_grid_startup_ready" not in logs


def test_stalled_status_fails_with_bounded_wait(capsys):
    with grid_endpoint() as grid:
        grid.delay = 1
        started = monotonic()
        with pytest.raises(TimeoutError) as raised:
            cleanup_grid(grid.url, timeout_seconds=0.2)
        assert monotonic() - started < 2
        assert isinstance(raised.value.__cause__, requests.Timeout)
    assert "transport_timeout" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("status", "payload", "error_type", "reason"),
    [
        (403, {}, requests.HTTPError, "http_error"),
        (503, {}, requests.HTTPError, "http_error"),
        (200, {}, TypeError, "invalid_status"),
        (200, {"value": {"ready": "false", "nodes": []}}, TypeError, "invalid_status"),
        (200, {"value": {"ready": True, "nodes": {}}}, TypeError, "invalid_status"),
        (200, {"value": {"ready": True, "nodes": [{}]}}, TypeError, "invalid_status"),
    ],
)
def test_bad_status_is_a_structured_startup_failure(
    status, payload, error_type, reason
):
    with grid_endpoint() as grid:
        grid.status = status
        grid.payload = payload
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; from app.utils.logging import configure_logging; "
                    "from app.utils.selenium import cleanup_grid; configure_logging(); "
                    "cleanup_grid(sys.argv[1], timeout_seconds=3)"
                ),
                grid.url,
            ],
            env={**os.environ, "LOG_FORMAT": "json"},
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert grid.requests == 1
    events = [
        json.loads(line) for line in result.stderr.splitlines() if line.startswith("{")
    ]
    failure = next(e for e in events if e["event"] == "selenium_grid_startup_failed")
    assert failure["reason"] == reason
    assert failure["error_type"] == error_type.__name__
    assert failure["http_status"] == (status if status != 200 else None)
    assert failure["timestamp"].endswith("Z")
    assert not any(e["event"] == "selenium_grid_startup_ready" for e in events)


def test_startup_removes_orphan_before_reporting_ready():
    with grid_endpoint() as grid:
        grid.payload["value"]["nodes"] = [
            {"slots": [{"session": {"sessionId": "old"}}]}
        ]
        cleanup_grid(grid.url, timeout_seconds=3)
        assert grid.deleted == ["/session/old"]
        assert grid.requests >= 2


async def test_cancelled_startup_stops_readiness_polling(capsys):
    with grid_endpoint() as grid:
        grid.payload["value"]["ready"] = False
        task = asyncio.create_task(prepare_grid(grid.url))
        try:
            assert await asyncio.to_thread(grid.requested.wait, 3)
        finally:
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.3)
        requests_after_stop = grid.requests
        await asyncio.sleep(0.3)
        assert grid.requests == requests_after_stop
    logs = capsys.readouterr().out
    assert "selenium_grid_startup_cancelled" in logs
    assert "selenium_grid_startup_ready" not in logs
