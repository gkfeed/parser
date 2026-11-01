import os
import socket
from concurrent.futures import CancelledError
from pathlib import Path
from threading import Event
from time import monotonic
from typing import cast, override
from urllib.parse import urlsplit, urlunsplit

import requests
import structlog
from selenium.webdriver.remote.client_config import ClientConfig
from selenium.webdriver.remote.remote_connection import RemoteConnection
from selenium.webdriver.remote.webdriver import WebDriver

from app.utils.logging import url_log_fields

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


def cleanup_grid(
    server_url: str,
    *,
    timeout_seconds: float = QUIT_TIMEOUT_SECONDS + GRID_RECOVERY_TIMEOUT_SECONDS,
    stop_event: Event | None = None,
) -> None:
    """Release sessions left by the previous, sole owner of this Grid."""
    started = monotonic()
    deadline = started + timeout_seconds
    stop_event = stop_event if stop_event is not None else Event()
    log = logger.bind(**url_log_fields(server_url, field="grid_url"))
    log.info("selenium_grid_startup_started", timeout_seconds=timeout_seconds)
    with requests.Session() as http:
        http.trust_env = False
        try:
            _cleanup_grid(http, server_url, deadline, stop_event)
        except CancelledError:
            log.info(
                "selenium_grid_startup_cancelled",
                duration_seconds=monotonic() - started,
            )
            raise
        except Exception as error:
            log.error(
                "selenium_grid_startup_failed",
                reason=_grid_error_reason(error),
                error_type=type(error).__name__,
                http_status=error.response.status_code
                if isinstance(error, requests.HTTPError) and error.response is not None
                else None,
                duration_seconds=monotonic() - started,
            )
            raise
    log.info("selenium_grid_startup_ready", duration_seconds=monotonic() - started)


def _cleanup_grid(
    http: requests.Session, server_url: str, deadline: float, stop_event: Event
) -> None:
    status_url = _grid_url(server_url, "/status")
    last_reason = None
    last_error = None
    while True:
        try:
            _remaining_timeout(deadline, stop_event)
            value = _grid_status(http, status_url, deadline)
            _remaining_timeout(deadline, stop_event)
        except requests.exceptions.SSLError:
            raise
        except (requests.ConnectionError, requests.Timeout) as error:
            value = None
            last_error = error
        except TimeoutError as error:
            logger.error("selenium_grid_readiness_timeout", last_reason=last_reason)
            raise TimeoutError("Selenium Grid startup deadline exceeded") from (
                last_error or error
            )
        reason = _grid_error_reason(last_error) if value is None else "not_ready"
        if value is not None:
            last_error = None
        sessions = _session_ids(value) if value is not None else []
        if value is not None and value["ready"] and not sessions:
            return
        if sessions:
            reason = "orphan_sessions"
        if reason != last_reason:
            logger.warning(
                "selenium_grid_waiting", reason=reason, sessions=len(sessions)
            )
            last_reason = reason
        for session_id in sessions:
            _remove_grid_session(http, server_url, session_id, deadline, stop_event)
        stop_event.wait(min(0.2, max(0, deadline - monotonic())))


def _remove_grid_session(
    http: requests.Session,
    server_url: str,
    session_id: str,
    deadline: float,
    stop_event: Event,
) -> None:
    try:
        response = http.delete(
            _grid_url(server_url, f"/session/{session_id}"),
            timeout=min(QUIT_TIMEOUT_SECONDS, _remaining_timeout(deadline, stop_event)),
        )
        response.raise_for_status()
    except requests.RequestException:
        _recover_grid_session(
            server_url, session_id, deadline=deadline, stop_event=stop_event
        )
    logger.info("selenium_orphan_session_removed", session_id=session_id)


def _grid_error_reason(error: BaseException | None) -> str:
    if isinstance(error, requests.Timeout):
        return "transport_timeout"
    if isinstance(error, requests.HTTPError):
        return "http_error"
    if isinstance(error, requests.exceptions.SSLError):
        return "tls_error"
    if isinstance(error, TimeoutError):
        return "deadline_exceeded"
    if isinstance(error, (ValueError, KeyError, TypeError)):
        return "invalid_status"
    cause = error
    while cause is not None:
        if isinstance(cause, ConnectionRefusedError):
            return "connection_refused"
        if isinstance(cause, socket.gaierror):
            return "dns_error"
        cause = cause.__cause__ or cause.__context__
    if isinstance(error, requests.ConnectionError):
        return "connection_error"
    return "cleanup_error"


def _grid_url(server_url: str, path: str) -> str:
    parts = urlsplit(server_url)
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _recover_grid_session(
    server_url: str,
    session_id: str,
    *,
    deadline: float | None = None,
    stop_event: Event | None = None,
) -> None:
    status_url = _grid_url(server_url, "/status")
    if deadline is None:
        deadline = monotonic() + GRID_RECOVERY_TIMEOUT_SECONDS
    stop_event = stop_event if stop_event is not None else Event()
    with requests.Session() as http:
        http.trust_env = False
        _remaining_timeout(deadline, stop_event)
        try:
            value = _grid_status(http, status_url, deadline)
        except requests.RequestException:
            value = None
        if value is not None and session_id not in _session_ids(value):
            return

        _remaining_timeout(deadline, stop_event)
        recovery_path = os.getenv("SELENIUM_RECOVERY_REQUEST_PATH")
        if not recovery_path:
            raise RuntimeError("Selenium Grid recovery watchdog is not configured")
        request_path = Path(recovery_path)
        temporary_path = request_path.with_suffix(".tmp")
        temporary_path.write_text(session_id)
        temporary_path.chmod(0o644)
        temporary_path.replace(request_path)

        while True:
            _remaining_timeout(deadline, stop_event)
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
            stop_event.wait(min(0.2, _remaining_timeout(deadline, stop_event)))


def _remaining_timeout(deadline: float, stop_event: Event | None = None) -> float:
    if stop_event is not None and stop_event.is_set():
        raise CancelledError("Selenium Grid startup cancelled")
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Selenium Grid did not release the session")
    return remaining


def _grid_status(http: requests.Session, status_url: str, deadline: float) -> dict:
    response = http.get(status_url, timeout=min(2, _remaining_timeout(deadline)))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("value"), dict):
        raise TypeError("Invalid Selenium Grid status value")
    value = payload["value"]
    if not isinstance(value.get("ready"), bool) or not isinstance(
        value.get("nodes"), list
    ):
        raise TypeError("Invalid Selenium Grid readiness or nodes")
    for node in value["nodes"]:
        if not isinstance(node, dict) or not isinstance(node.get("slots"), list):
            raise TypeError("Invalid Selenium Grid node slots")
    return value


def _session_ids(status: dict) -> list[str]:
    return [
        slot["session"]["sessionId"]
        for node in status["nodes"]
        for slot in node["slots"]
        if slot.get("session")
    ]
