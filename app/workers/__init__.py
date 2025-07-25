from typing import Callable, Awaitable

from app.configs.env import IS_WORKER
from app.services.queue import QueueService


def worker(func) -> Callable[..., Awaitable]:
    async def wrapper(*args, **kwargs):
        if IS_WORKER:
            return await func(*args, **kwargs)
        return await QueueService.put_and_wait_for_result(func, args)

    return wrapper


def worker_sync(func) -> Callable[..., Awaitable]:
    async def wrapper(*args, **kwargs):
        if IS_WORKER:
            return await func(*args, **kwargs)
        return await QueueService.put_and_wait_for_result_sync(func, args)

    return wrapper
