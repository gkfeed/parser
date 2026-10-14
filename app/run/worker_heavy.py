import asyncio
import signal

from app.configs.env import SELENIUM_DOCKER_URL
from app.configs.workers import heavy_parsers
from app.core.worker import run_worker
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

    if IS_IN_DOCKER:
        await asyncio.to_thread(cleanup_grid, SELENIUM_DOCKER_URL)

    while True:
        for parser_type in heavy_parsers:
            await run_worker(parser_type)


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        pass
