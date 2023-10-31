import asyncio
from typing import Callable, Any

from redis import Redis
from rq import Queue

from app.settings import REDIS_HOST, IS_WORKER


class QueueService:
    __rq_default = Queue(connection=Redis(host=REDIS_HOST))
    __rq_sync = Queue(name="sync", connection=Redis(host=REDIS_HOST))

    @classmethod
    async def put_and_wait_for_result(cls, func: Callable, args: list[Any]) -> Any:
        return await cls._put_and_wait_for_result(func, args, cls.__rq_default)

    @classmethod
    async def put_and_wait_for_result_sync(cls, func: Callable, args: list[Any]) -> Any:
        return await cls._put_and_wait_for_result(func, args, cls.__rq_sync)

    @classmethod
    async def _put_and_wait_for_result(
        cls, func: Callable, args: list[Any], queue: Queue
    ) -> Any:
        job = queue.enqueue(func, *args)
        while not job.is_finished:
            if job.is_failed:
                raise ValueError
            await asyncio.sleep(1)
        return job.result


def async_queue_wrap(func):
    async def wrapper(*args, **kwargs):
        if IS_WORKER:
            return func(*args)
        return await QueueService.put_and_wait_for_result(func, args)

    return wrapper


def async_run_sync_in_queue(func):
    async def wrapper(*args, **kwargs):
        if IS_WORKER:
            return func(*args)
        return await QueueService.put_and_wait_for_result_sync(func, args)

    return wrapper
