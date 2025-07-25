import asyncio
from typing import Callable, Any, Sequence

from redis import Redis
from rq import Queue

from app.configs.env import REDIS_HOST


class QueueService:
    __rq_default = Queue(connection=Redis(host=REDIS_HOST))
    __rq_sync = Queue(name="sync", connection=Redis(host=REDIS_HOST))

    @classmethod
    async def put_and_wait_for_result(cls, func: Callable, args: Sequence[Any]) -> Any:
        return await cls._put_and_wait_for_result(func, args, cls.__rq_default)

    @classmethod
    async def put_and_wait_for_result_sync(
        cls, func: Callable, args: Sequence[Any]
    ) -> Any:
        return await cls._put_and_wait_for_result(func, args, cls.__rq_sync)

    @classmethod
    async def _put_and_wait_for_result(
        cls, func: Callable, args: Sequence[Any], queue: Queue
    ) -> Any:
        job = queue.enqueue(func, *args)
        while not job.is_finished:
            if job.is_failed:
                raise ValueError
            await asyncio.sleep(1)
        return job.result
