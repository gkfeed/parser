from datetime import datetime

import pytest

from app.serializers.feed import Item
from app.services.hash import HashService


def test_hash_consistency():
    """
    Test that the same dataclass instance always produces the same hash.
    """
    instance = Item(
        title="test_title",
        link="test_link",
        text="test_text",
        date=datetime.fromisoformat("2024-01-01T00:00:00"),
    )
    hash1 = HashService.hash_item(instance)
    hash2 = HashService.hash_item(instance)
    assert hash1 == hash2, "Hash should be consistent for the same dataclass instance."


def test_hash_uniqueness():
    """
    Test that two dataclass instances with different values produce different hashes.
    """
    instance1 = Item(
        title="test_title1",
        link="test_link1",
        text="test_text1",
        date=datetime.fromisoformat("2024-01-01T00:00:00"),
    )
    instance2 = Item(
        title="test_title2",
        link="test_link2",
        text="test_text2",
        date=datetime.fromisoformat("2024-01-02T00:00:00"),
    )
    hash1 = HashService.hash_item(instance1)
    hash2 = HashService.hash_item(instance2)
    assert hash1 != hash2, "Different dataclass values should yield different hashes."


def test_invalid_input():
    """
    Test that only Item instances can be hashed.
    """
    with pytest.raises(Exception):
        HashService.hash_item("not an Item instance")


def test_order_independence():
    """
    Test that the hash remains the same regardless of the order of fields,
    given that JSON serialization sorts keys.
    """

    instance1 = Item(
        title="test_title1",
        link="test_link1",
        text="test_text1",
        date=datetime.fromisoformat("2024-01-01T00:00:00"),
    )

    instance2 = Item(
        date=datetime.fromisoformat("2024-01-01T00:00:00"),
        text="test_text1",
        link="test_link1",
        title="test_title1",
    )

    hash1 = HashService.hash_item(instance1)
    hash2 = HashService.hash_item(instance2)
    assert hash1 == hash2
