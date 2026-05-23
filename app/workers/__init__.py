from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


def worker(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    return wrapper


def worker_sync(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    return wrapper
