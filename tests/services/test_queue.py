import pytest


async def _async_add(a: int, b: int) -> int:
    return a + b


@pytest.mark.skip(reason='meaningless with mocks without works not in CI')
async def test_get_result():
    from app.services.queue import QueueService

    expected_result = 3

    result = await QueueService.put_and_wait_for_result(_async_add, [1, 2])

    assert result == expected_result
