import asyncio

from app.configs.workers import heavy_parsers
from app.core.worker import run_workers

if __name__ == "__main__":
    asyncio.run(run_workers(heavy_parsers))
