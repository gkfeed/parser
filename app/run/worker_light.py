import asyncio
import os
import signal
from collections.abc import Iterator
from itertools import cycle

from app.configs.workers import light_parsers
from app.core.worker import run_worker
from app.utils.logging import configure_logging


async def _run_slot(parser_types: Iterator[str]) -> None:
    while True:
        await run_worker(next(parser_types))


async def main() -> None:
    concurrency = int(os.getenv("LIGHT_WORKER_CONCURRENCY", "4"))
    if concurrency < 1:
        raise ValueError("LIGHT_WORKER_CONCURRENCY must be greater than zero")
    if not light_parsers:
        raise ValueError("No light parsers configured")

    task = asyncio.current_task()
    assert task is not None

    def stop() -> None:
        if not task.cancelling():
            task.cancel()

    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop)

    parser_types = cycle(light_parsers)
    async with asyncio.TaskGroup() as tasks:
        for _ in range(concurrency):
            tasks.create_task(_run_slot(parser_types))


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        pass
