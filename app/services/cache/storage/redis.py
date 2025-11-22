from typing import Any, cast
import pickle
import redis
from app.configs.env import REDIS_HOST

from ._base import BaseStorage


class RedisStorage(BaseStorage):
    def __init__(self, client: redis.Redis | None = None) -> None:
        self.__client = client or redis.Redis(host=REDIS_HOST)

    def get(self, id: str) -> Any:
        value = self.__client.get(id)
        if value is None:
            raise ValueError("No such index: " + id)
        return pickle.loads(cast(bytes, value))

    def set(self, id: str, data: Any) -> None:
        self.__client.set(id, pickle.dumps(data))
