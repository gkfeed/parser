import random

import pytest

from app.services.cache import CacheService
from app.services.cache.storage.memory import MemoryStorage


def test_creating_cache_service():
    CacheService(MemoryStorage())


def test_add_data_to_cache():
    cache: CacheService[str] = CacheService(MemoryStorage())
    cache.set('0', '0')


def test_data_storing_in_cache():
    cache: CacheService[int] = CacheService(MemoryStorage())
    test_data = []
    [
        test_data.append(random.randint(0, 1000))
        for _ in range(100)
    ]
    [
        cache.set(str(n), i)
        for n, i in enumerate(test_data)

    ]
    for n, i in enumerate(test_data):
        assert cache.get(str(n)) == i


def test_get_undefined_value():
    cache: CacheService[int] = CacheService(MemoryStorage())
    with pytest.raises(ValueError):
        id = str(random.randint(0, 1000))
        cache.get(id)


def test_unique_of_different_caches():
    cache_a: CacheService[int] = CacheService(MemoryStorage())
    cache_b: CacheService[int] = CacheService(MemoryStorage())

    cache_a.set('0', 0)
    with pytest.raises(ValueError):
        cache_b.get('0')
