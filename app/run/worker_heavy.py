import asyncio
import os
import signal
from pathlib import Path

from app.configs.env import BROKER_URL, SELENIUM_DOCKER_URL
from app.configs.workers import heavy_parsers
from app.core.worker import recover_worker_task, run_worker
from app.services.broker import BrokerService
from app.utils.is_in_docker import IS_IN_DOCKER
from app.utils.logging import configure_logging
from app.utils.selenium import cleanup_grid


async def main() -> None:
    task = asyncio.current_task()
    assert task is not None

    def stop() -> None:
        if not task.cancelling():
            task.cancel()

    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop)

    recovery_path = os.getenv("SELENIUM_RECOVERY_REQUEST_PATH")
    task_path = Path(recovery_path).with_name("active-task") if recovery_path else None
    if IS_IN_DOCKER:
        await asyncio.to_thread(cleanup_grid, SELENIUM_DOCKER_URL)
    await recover_worker_task(BrokerService(BROKER_URL), task_path)

    while True:
        for parser_type in heavy_parsers:
            await run_worker(parser_type, active_task_path=task_path)


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        pass
