from typing import Any

from app.settings import IS_WORKER
from app.services.container import Container

if IS_WORKER:
    import app.configs


def inject(params: dict[str, Any], call: bool = False):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for param in params:
                injected_value = getattr(Container.get_data(), params[param])
                if call:
                    injected_value = injected_value()
                kwargs[param] = injected_value

            return func(*args, **kwargs)

        return wrapper

    return decorator


def inject_async(params: dict[str, Any], call: bool = False):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for param in params:
                injected_value = getattr(Container.get_data(), params[param])
                if call:
                    injected_value = injected_value()
                kwargs[param] = injected_value

            return await func(*args, **kwargs)

        return wrapper

    return decorator
