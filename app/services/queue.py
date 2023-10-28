import asyncio
from typing import Callable, Any

from redis import Redis
from rq import Queue

from app.settings import REDIS_HOST, IS_WORKER


class QueueService:
    __rq = Queue(connection=Redis(host=REDIS_HOST))

    @classmethod
    async def put_and_wait_for_result(cls, func: Callable, args=list[Any]) -> Any:
        job = cls.__rq.enqueue(func, *args)
        while not job.is_finished:
            if job.is_failed:
                raise ValueError
            await asyncio.sleep(1)
        return job.result


def async_queue_wrap(func):
    async def wrapper(*args, **kwargs):
        print(type(IS_WORKER))
        if IS_WORKER:
            return func(*args[1:])
        return await QueueService.put_and_wait_for_result(func, args)

    return wrapper
