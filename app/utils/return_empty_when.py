def async_return_empty_when(*args: list[Exception]):
    exceptions = tuple(args)

    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
            except* exceptions:
                result = []
            return result

        return wrapper

    return decorator
