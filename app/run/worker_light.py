import asyncio

from app.configs.workers import light_parsers
from app.core.worker import run_worker
from app.utils.logging import configure_logging

if __name__ == "__main__":
    configure_logging()
    while True:
        for parser_type in light_parsers:
            asyncio.run(run_worker(parser_type))
