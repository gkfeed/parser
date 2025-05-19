import pytest

from app.services.container import Container
from app.utils.inject import inject


def test_sync_injection(monkeypatch):
    class MockData:
        foo = 42

    monkeypatch.setattr(Container, "get_data", lambda: MockData())

    @inject({"arg": "foo"})
    def sync_func(**kwargs):
        return kwargs

    result = sync_func()
    assert result["arg"] == 42


def test_sync_injection_with_call(monkeypatch):
    class MockData:
        foo = lambda _: 100

    monkeypatch.setattr(Container, "get_data", lambda: MockData())

    @inject(params={"arg": "foo"}, call=True)
    def sync_func(**kwargs):
        return kwargs

    result = sync_func()
    assert result["arg"] == 100


async def test_async_injection(monkeypatch):
    class MockData:
        foo = 42

    monkeypatch.setattr(Container, "get_data", lambda: MockData())

    @inject(params={"arg": "foo"})
    async def async_func(**kwargs):
        return kwargs

    result = await async_func()
    assert result["arg"] == 42


async def test_async_injection_with_call(monkeypatch):
    class MockData:
        foo = lambda _: 100

    monkeypatch.setattr(Container, "get_data", lambda: MockData())

    @inject(params={"arg": "foo"}, call=True)
    async def async_func(**kwargs):
        return kwargs

    result = await async_func()
    assert result["arg"] == 100


def test_missing_attribute_raises_error(monkeypatch):
    class MockData:
        pass

    monkeypatch.setattr(Container, "get_data", lambda: MockData())

    @inject(params={"arg": "foo"})
    def sync_func(**kwargs):
        return kwargs

    with pytest.raises(AttributeError):
        sync_func()


def test_injection_overrides_existing_kwarg(monkeypatch):
    class MockData:
        foo = 42

    monkeypatch.setattr(Container, "get_data", lambda: MockData())

    @inject(params={"arg": "foo"})
    def sync_func(**kwargs):
        return kwargs

    result = sync_func(arg=None)
    assert result["arg"] == 42
