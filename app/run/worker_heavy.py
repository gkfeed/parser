import asyncio

from app.core.worker import run_worker
from . import heavy_parsers

if __name__ == "__main__":
    while True:
        for parser_type in heavy_parsers:
            asyncio.run(run_worker(parser_type))
