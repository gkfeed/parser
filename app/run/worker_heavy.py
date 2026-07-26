import asyncio

from app.configs.workers import heavy_parsers
from app.core.worker import run_worker

if __name__ == "__main__":
    while True:
        for parser_type in heavy_parsers:
            asyncio.run(run_worker(parser_type))
