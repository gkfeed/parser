"""Restart standalone Grid after a worker's failed session cleanup."""

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

REQUEST_PATH = Path("/selenium-recovery/request")


def should_restart(session_id: str, *, allow_unreachable: bool) -> bool:
    try:
        with urllib.request.urlopen(
            "http://localhost:4444/status", timeout=2
        ) as response:
            status = json.load(response)["value"]
    except (OSError, urllib.error.URLError, ValueError):
        # The worker already failed cleanup. An unreachable Grid needs recovery too.
        return allow_unreachable
    return any(
        (slot.get("session") or {}).get("sessionId") == session_id
        for node in status["nodes"]
        for slot in node["slots"]
    )


def main() -> int:
    grid = subprocess.Popen(["/opt/bin/entry_point.sh"], start_new_session=True)
    started = time.monotonic()

    def stop(_signum: int, _frame: object) -> None:
        os.killpg(grid.pid, signal.SIGTERM)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while grid.poll() is None:
        try:
            session_id = REQUEST_PATH.read_text().strip()
        except FileNotFoundError:
            session_id = ""
        if session_id and should_restart(
            session_id, allow_unreachable=time.monotonic() - started >= 20
        ):
            print(
                json.dumps(
                    {
                        "event": "selenium_grid_restart_requested",
                        "session_id": session_id,
                    }
                ),
                flush=True,
            )
            # Exiting PID 1 kills the whole container, including stuck drivers.
            # Docker's restart policy starts a fresh Grid. The worker removes its
            # request after readiness; old requests never match a new session.
            return 1
        time.sleep(0.2)
    return grid.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
