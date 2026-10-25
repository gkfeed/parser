"""Measure public atomic persistence on a disposable canonical PostgreSQL database.

Restore infra/db/schema.sql first, set ITEM_BATCH_TEST_DATABASE_URL, then run:
    uv run python -m scripts.benchmark_item_deduplication --baseline-ref a532e11

Each sample owns a new user/feed and removes it afterward. Results are CSV;
SELECT counts are measurements, never assertions. The baseline executes trusted
repository source from the supplied git revision using the same session factory.
"""

import argparse
import asyncio
import importlib.util
import logging
import os
import subprocess
import tempfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4

import structlog
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.serializers.feed import Feed, Item
from app.services.repositories.item import ItemsRepository


def baseline_repository(revision):
    source = subprocess.check_output(
        ["git", "show", f"{revision}:app/services/repositories/item.py"], text=True
    )
    with tempfile.TemporaryDirectory(prefix="parser-dedup-baseline-") as directory:
        path = Path(directory) / "item.py"
        path.write_text(source)
        spec = importlib.util.spec_from_file_location(
            "app.services.repositories._dedup_baseline", path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load baseline repository")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ItemsRepository


@asynccontextmanager
async def fixture_feed(engine, history, size, scenario):
    async with engine.begin() as connection:
        user_id = await connection.scalar(
            text("INSERT INTO users (name) VALUES (:name) RETURNING id"),
            {"name": f"dedup-benchmark-{uuid4()}"},
        )
        feed_id = await connection.scalar(
            text(
                "INSERT INTO feed (title, url, type, user_id) "
                "VALUES ('Benchmark', 'https://benchmark.test', 'test', :user) RETURNING id"
            ),
            {"user": user_id},
        )
    try:
        total = history + (size if scenario != "new" else 0)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO item (feed_id, title, text, date, link) "
                    "SELECT :feed, 'Item ' || i, repeat('body ', 40) || i, now(), "
                    "'https://benchmark.test/' || i FROM generate_series(0, :last) AS i"
                ),
                {"feed": feed_id, "last": total - 1},
            )
            await connection.execute(
                text(
                    "INSERT INTO item_hash (feed_id, hash) SELECT :feed, 'hash-' || i "
                    "FROM generate_series(0, :last) AS i"
                ),
                {"feed": feed_id, "last": total - 1},
            )
            await connection.execute(text("ANALYZE item"))
            await connection.execute(text("ANALYZE item_hash"))
        yield Feed(
            id=feed_id, title="Benchmark", url="https://benchmark.test", type="test"
        )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM feed WHERE id = :id"), {"id": feed_id}
            )
            await connection.execute(
                text("DELETE FROM users WHERE id = :id"), {"id": user_id}
            )

        # Keep dead tuples from earlier samples out of later timing measurements.
        async with engine.connect() as connection:
            await connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.exec_driver_sql("VACUUM (ANALYZE) item")
            await connection.exec_driver_sql("VACUUM (ANALYZE) item_hash")
            await connection.exec_driver_sql("VACUUM (ANALYZE) item_changes")


def incoming_items(history, size, scenario):
    start = history if scenario == "new" else 0
    hash_prefix = "fresh-" if scenario == "fallback" else "hash-"
    return [
        Item(
            title=f"Item {index}",
            text="body " * 40 + str(index),
            date=datetime(2026, 9, 15, tzinfo=UTC),
            link=f"https://benchmark.test/{index}",
            hash=f"{hash_prefix}{index}",
        )
        for index in range(start, start + size)
    ]


async def sample(engine, repository, history, size, scenario):
    statements = []

    def record(_conn, _cursor, statement, parameters, _context, _many):
        statements.append((statement, parameters))

    async with fixture_feed(engine, history, size, scenario) as feed:
        items = incoming_items(history, size, scenario)
        event.listen(engine.sync_engine, "before_cursor_execute", record)
        try:
            started = perf_counter()
            returned = await repository.save_parser_result(
                feed, items, datetime(2026, 9, 16, tzinfo=UTC)
            )
            elapsed = (perf_counter() - started) * 1000
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", record)
        expected = [] if scenario == "known" else items
        if returned != expected:
            raise ValueError("Benchmark persistence returned unexpected items")
        reads = [
            (sql, params) for sql, params in statements if sql.startswith("SELECT")
        ]
        return len(reads), len(statements), elapsed


async def run(args):
    if not args.url:
        raise ValueError(
            "Set ITEM_BATCH_TEST_DATABASE_URL to a disposable canonical PostgreSQL DB"
        )
    if args.repeats < 1 or min(args.histories) < 0 or min(args.sizes) < 1:
        raise ValueError("Repetitions/sizes must be positive and histories nonnegative")
    engine = create_async_engine(args.url)
    if engine.dialect.name != "postgresql":
        raise ValueError("This benchmark requires PostgreSQL")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    repositories = [
        (args.baseline_ref, baseline_repository(args.baseline_ref)(sessions)),
        ("working-tree", ItemsRepository(sessions)),
    ]
    print("revision,history,batch,scenario,selects,statements,median_ms", flush=True)
    try:
        for history, size, scenario, (revision, repository) in product(
            args.histories, args.sizes, ("new", "known", "fallback"), repositories
        ):
            results = [
                await sample(engine, repository, history, size, scenario)
                for _ in range(args.repeats)
            ]
            reads, statements, elapsed = zip(*results)
            print(
                f"{revision},{history},{size},{scenario},{median(reads):g},{median(statements):g},{median(elapsed):.2f}",
                flush=True,
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("ITEM_BATCH_TEST_DATABASE_URL"))
    parser.add_argument("--baseline-ref", default="a532e11")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--histories", type=int, nargs="+", default=[0, 10000])
    parser.add_argument("--sizes", type=int, nargs="+", default=[10, 100, 1000])
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR)
    )
    asyncio.run(run(parser.parse_args()))
