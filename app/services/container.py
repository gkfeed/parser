class Container[T]:
    __data: T

    @classmethod
    def setup(cls, data: T):
        cls.__data = data

    @classmethod
    def get_data(cls) -> T:
        return cls.__data
