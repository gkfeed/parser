import os
from pathlib import Path
from time import monotonic, sleep
from typing import cast, override
from urllib.parse import urlsplit, urlunsplit

import requests
import structlog
from selenium.webdriver.remote.client_config import ClientConfig
from selenium.webdriver.remote.remote_connection import RemoteConnection
from selenium.webdriver.remote.webdriver import WebDriver

logger = structlog.get_logger(__name__)

QUIT_TIMEOUT_SECONDS = 10
GRID_RECOVERY_TIMEOUT_SECONDS = 30


class GridWebDriver(WebDriver):
    @override
    def quit(self) -> None:
        connection = cast(RemoteConnection, self.command_executor)
        client_config = cast(ClientConfig, connection.client_config)
        server_url = client_config.remote_server_addr
        session_id = self.session_id
        if session_id is None:
            connection.close()
            return
        client_config.timeout = QUIT_TIMEOUT_SECONDS
        try:
            super().quit()
        except Exception as error:
            logger.warning(
                "selenium_quit_failed",
                session_id=session_id,
                error_type=type(error).__name__,
                exc_info=True,
            )
            try:
                _recover_grid_session(server_url, session_id)
            except Exception as recovery_error:
                logger.error(
                    "selenium_grid_recovery_failed",
                    session_id=session_id,
                    error_type=type(recovery_error).__name__,
                )
                raise error from recovery_error
            logger.info("selenium_grid_recovered", session_id=session_id)


def cleanup_grid(server_url: str) -> None:
    """Release sessions left by the previous, sole owner of this Grid."""
    status_url = _grid_url(server_url, "/status")
    deadline = monotonic() + QUIT_TIMEOUT_SECONDS + GRID_RECOVERY_TIMEOUT_SECONDS
    with requests.Session() as http:
        http.trust_env = False
        while True:
            value = _grid_status(http, status_url, deadline)
            sessions = _session_ids(value)
            if value.get("ready") and not sessions:
                return
            for session_id in sessions:
                try:
                    response = http.delete(
                        _grid_url(server_url, f"/session/{session_id}"),
                        timeout=min(QUIT_TIMEOUT_SECONDS, _remaining_timeout(deadline)),
                    )
                    response.raise_for_status()
                except requests.RequestException:
                    _recover_grid_session(server_url, session_id, deadline=deadline)
                logger.info("selenium_orphan_session_removed", session_id=session_id)
            sleep(min(0.2, _remaining_timeout(deadline)))


def _grid_url(server_url: str, path: str) -> str:
    parts = urlsplit(server_url)
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _recover_grid_session(
    server_url: str, session_id: str, *, deadline: float | None = None
) -> None:
    status_url = _grid_url(server_url, "/status")
    if deadline is None:
        deadline = monotonic() + GRID_RECOVERY_TIMEOUT_SECONDS
    with requests.Session() as http:
        http.trust_env = False
        try:
            value = _grid_status(http, status_url, deadline)
        except requests.RequestException:
            value = None
        if value is not None and session_id not in _session_ids(value):
            return

        recovery_path = os.getenv("SELENIUM_RECOVERY_REQUEST_PATH")
        if not recovery_path:
            raise RuntimeError("Selenium Grid recovery watchdog is not configured")
        request_path = Path(recovery_path)
        temporary_path = request_path.with_suffix(".tmp")
        temporary_path.write_text(session_id)
        temporary_path.chmod(0o644)
        temporary_path.replace(request_path)

        while True:
            _remaining_timeout(deadline)
            try:
                value = _grid_status(http, status_url, deadline)
            except requests.RequestException:
                value = None
            if (
                value is not None
                and value.get("ready")
                and session_id not in _session_ids(value)
            ):
                request_path.unlink(missing_ok=True)
                return
            sleep(min(0.2, _remaining_timeout(deadline)))


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Selenium Grid did not release the session")
    return remaining


def _grid_status(http: requests.Session, status_url: str, deadline: float) -> dict:
    response = http.get(status_url, timeout=min(2, _remaining_timeout(deadline)))
    response.raise_for_status()
    return response.json()["value"]


def _session_ids(status: dict) -> list[str]:
    return [
        slot["session"]["sessionId"]
        for node in status["nodes"]
        for slot in node["slots"]
        if slot.get("session")
    ]
