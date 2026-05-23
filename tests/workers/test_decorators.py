from app.workers import worker, worker_sync


async def test_worker_executes_function_directly():
    @worker
    async def add(a: int, b: int) -> int:
        return a + b

    assert await add(1, 2) == 3


async def test_worker_sync_executes_function_directly():
    @worker_sync
    async def add(a: int, b: int) -> int:
        return a + b

    assert await add(1, 2) == 3
