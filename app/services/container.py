from typing import Any


class Container:
    __data: Any

    @classmethod
    def setup(cls, data: Any):
        cls.__data = data

    @classmethod
    def get_data(cls) -> Any:
        return cls.__data
