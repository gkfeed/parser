import asyncio
import signal

from app.configs.workers import light_parsers
from app.core.worker import run_worker
from app.utils.logging import configure_logging


async def main() -> None:
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

    while True:
        for parser_type in light_parsers:
            await run_worker(parser_type)


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        pass
