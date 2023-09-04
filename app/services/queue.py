import asyncio
from typing import Coroutine, Any

from redis import Redis
from rq import Queue

from app.settings import REDIS_HOST


class QueueService:
    __rq = Queue(connection=Redis(host=REDIS_HOST))

    @classmethod
    async def put_and_wait_for_result(cls,
                                      func: Coroutine, args=list[Any]) -> Any:
        job = cls.__rq.enqueue(func, *args)
        while not job.is_finished:
            if job.is_failed:
                raise ValueError
            await asyncio.sleep(1)
        return job.result
