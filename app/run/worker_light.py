import asyncio

from app.core.worker import run_worker
from . import light_parsers

if __name__ == "__main__":
    while True:
        for parser_type in light_parsers:
            asyncio.run(run_worker(parser_type))
