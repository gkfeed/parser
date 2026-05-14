import os
from typing import Any

import pytest
from dotenv import load_dotenv

from app.services.cache.storage._base import BaseStorage


load_dotenv(os.path.join(os.path.dirname(__file__), ".env.test"), override=True)


class MockStorage(BaseStorage):
    def __init__(self):
        self.data = {}

    def get(self, id: str) -> Any:
        if id not in self.data:
            raise ValueError("No such index: " + id)
        return self.data[id]

    def set(self, id: str, data: Any) -> None:
        self.data[id] = data


@pytest.fixture(autouse=True)
def mock_cache_extension(monkeypatch):
    from app.services.cache.temporary import TemporaryCacheService
    from app.services.cache.use_temporary import UseTemporaryCacheServiceExtension

    # Create a new service with mock storage
    mock_service = TemporaryCacheService(storage=MockStorage())

    # Patch the class attribute 'cache' on UseTemporaryCacheServiceExtension
    monkeypatch.setattr(UseTemporaryCacheServiceExtension, "cache", mock_service)


@pytest.fixture(autouse=True)
def disable_external_selenium_fallback(monkeypatch):
    monkeypatch.setattr(
        "app.services.selenium.FALLBACK_TO_EXTERNAL_SELENIUM",
        False,
    )
