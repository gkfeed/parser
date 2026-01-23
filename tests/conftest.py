import pytest
from app.services.cache.use_temporary import UseTemporaryCacheServiceExtension
from app.services.cache.temporary import TemporaryCacheService


class MockStorage:
    def __init__(self):
        self.data = {}

    def get(self, id: str):
        if id not in self.data:
            raise ValueError("No such index: " + id)
        return self.data[id]

    def set(self, id: str, data):
        self.data[id] = data


@pytest.fixture(autouse=True)
def mock_cache_extension(monkeypatch):
    # Create a new service with mock storage
    mock_service = TemporaryCacheService(storage=MockStorage())

    # Patch the class attribute 'cache' on UseTemporaryCacheServiceExtension
    monkeypatch.setattr(UseTemporaryCacheServiceExtension, "cache", mock_service)
