from typing import Any
import inspect

from app.configs.env import IS_WORKER
from app.services.container import Container

if IS_WORKER:
    import app.configs  # noqa: F401


def inject(params: dict[str, Any], call: bool = False):
    def decorator(func):
        is_async = inspect.iscoroutinefunction(func)

        def _inject_kwargs(kwargs):
            for param in params:
                injected_value = getattr(Container.get_data(), params[param])
                if call:
                    injected_value = injected_value()
                kwargs[param] = injected_value

        def wrapper(*args, **kwargs):
            _inject_kwargs(kwargs)
            return func(*args, **kwargs)

        async def async_wrapper(*args, **kwargs):
            _inject_kwargs(kwargs)
            return await func(*args, **kwargs)

        if is_async:
            return async_wrapper
        return wrapper

    return decorator
