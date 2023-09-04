from datetime import timedelta
import random
import time as time_

import pytest

from app.services.cache.temporary import \
    TemporaryCacheService, UndefinedCache, ExpiredCache
from app.services.cache.storage.memory import MemoryStorage


def test_create():
    TemporaryCacheService(MemoryStorage())


def test_set_data():
    cache: TemporaryCacheService[int] = TemporaryCacheService(MemoryStorage())
    num = random.randint(0, 1000)
    cache.set('0', num, timedelta(seconds=1))


def test_get_data():
    cache: TemporaryCacheService[int] = TemporaryCacheService(MemoryStorage())
    num = random.randint(0, 1000)
    cache.set('0', num, timedelta(hours=1))
    assert cache.get('0') == num


def test_undefined_cache():
    cache: TemporaryCacheService[int] = TemporaryCacheService(MemoryStorage())
    with pytest.raises(UndefinedCache):
        cache.get('0')


def test_cache_temporary():
    cache: TemporaryCacheService[int] = TemporaryCacheService(MemoryStorage())
    num = random.randint(0, 1000)
    cache.set('0', num, timedelta(microseconds=1))
    time_.sleep(0.01)
    with pytest.raises(ExpiredCache):
        assert cache.get('0') == num
