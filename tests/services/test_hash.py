import pytest

from app.services.hash import HashService


def test_hash_consistency():
    """
    Test that the same string always produces the same hash.
    """
    content = "test_content"
    hash1 = HashService.hash_str(content)
    hash2 = HashService.hash_str(content)
    assert hash1 == hash2, "Hash should be consistent for the same string."


def test_hash_uniqueness():
    """
    Test that two different strings produce different hashes.
    """
    content1 = "test_content1"
    content2 = "test_content2"
    hash1 = HashService.hash_str(content1)
    hash2 = HashService.hash_str(content2)
    assert hash1 != hash2, "Different strings should yield different hashes."


def test_invalid_input():
    """
    Test that non-string input raises an exception.
    """
    with pytest.raises(AttributeError):
        HashService.hash_str(123)  # type: ignore


def test_empty_string():
    """
    Test that hashing an empty string produces a valid hash.
    """
    hash_val = HashService.hash_str("")
    assert isinstance(hash_val, str)
    assert len(hash_val) > 0
