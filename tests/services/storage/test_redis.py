import pytest
import random
import fakeredis
from app.services.cache.storage.redis import RedisStorage


@pytest.fixture
def redis_storage():
    # Use fakeredis for testing
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)
    yield storage
    client.flushall() # Clear data after each test


def test_redis_storage_set_get(redis_storage):
    key = "test_key"
    value = "test_value"
    redis_storage.set(key, value)
    assert redis_storage.get(key) == value


def test_redis_storage_get_non_existent(redis_storage):
    key = "non_existent_key"
    with pytest.raises(ValueError):
        redis_storage.get(key)

def test_data_storing_in_cache(redis_storage):
    test_data = []
    [test_data.append(random.randint(0, 1000)) for _ in range(100)]
    [redis_storage.set(str(n), i) for n, i in enumerate(test_data)]
    for n, i in enumerate(test_data):
        assert redis_storage.get(str(n)) == i
