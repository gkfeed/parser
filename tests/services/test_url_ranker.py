import json
import os
from datetime import datetime, timedelta

import pytest

from app.services.url_ranker import URLRanker


@pytest.fixture
def temp_data_file(tmp_path):
    file_path = tmp_path / "test_ranks.json"
    yield str(file_path)
    if os.path.exists(file_path):
        os.remove(file_path)


@pytest.fixture
def url_ranker(temp_data_file):
    return URLRanker(temp_data_file)


def test_initialization_empty_file(url_ranker):
    assert url_ranker.ranks == {}
    assert url_ranker.last_failed == {}


def test_initialization_with_existing_data(temp_data_file):
    initial_data = {
        "ranks": {"url1": 1, "url2": 0},
        "last_failed": {"url1": datetime.now().timestamp()},
    }
    with open(temp_data_file, "w") as f:
        json.dump(initial_data, f)

    ranker = URLRanker(temp_data_file)
    assert ranker.ranks == {"url1": 1, "url2": 0}
    assert "url1" in ranker.last_failed
    assert "url2" not in ranker.last_failed


def test_save_ranks(url_ranker, temp_data_file):
    url_ranker.ranks = {"urlA": 5, "urlB": 2}
    url_ranker.last_failed = {"urlA": datetime.now().timestamp()}
    url_ranker.save_ranks()

    with open(temp_data_file, "r") as f:
        data = json.load(f)
    assert data["ranks"] == {"urlA": 5, "urlB": 2}
    assert "urlA" in data["last_failed"]
    assert "urlB" not in data["last_failed"]


def test_get_ranked_urls_new_urls(url_ranker):
    urls = ["urlC", "urlA", "urlB"]
    ranked_urls = url_ranker.get_ranked_urls(urls)
    assert ranked_urls == ["urlC", "urlA", "urlB"]  # Default rank 0, order preserved
    assert url_ranker.ranks == {"urlC": 0, "urlA": 0, "urlB": 0}


def test_get_ranked_urls_existing_ranks(url_ranker):
    url_ranker.ranks = {"urlX": 2, "urlY": 0, "urlZ": 1}
    urls = ["urlY", "urlX", "urlZ"]
    ranked_urls = url_ranker.get_ranked_urls(urls)
    assert ranked_urls == ["urlY", "urlZ", "urlX"]


def test_get_ranked_urls_with_cooldown(url_ranker):
    # Set a URL to have failed recently
    failed_time = datetime.now() - timedelta(minutes=30)
    url_ranker.last_failed = {"cooldown_url": failed_time.timestamp()}
    url_ranker.cooldown_minutes = 60

    urls = ["normal_url", "cooldown_url"]
    ranked_urls = url_ranker.get_ranked_urls(urls)
    assert ranked_urls == ["normal_url"]  # cooldown_url should be filtered out

    # Test after cooldown period
    past_failed_time = datetime.now() - timedelta(minutes=90)
    url_ranker.last_failed = {"cooldown_url": past_failed_time.timestamp()}
    ranked_urls_after_cooldown = url_ranker.get_ranked_urls(urls)
    assert "cooldown_url" in ranked_urls_after_cooldown


def test_demote_url(url_ranker):
    url_ranker.ranks = {"url1": 0}
    url_ranker.demote_url("url1")
    assert url_ranker.ranks["url1"] == 1
    assert "url1" in url_ranker.last_failed

    url_ranker.demote_url("new_url")
    assert url_ranker.ranks["new_url"] == 1
    assert "new_url" in url_ranker.last_failed


def test_promote_url(url_ranker):
    url_ranker.ranks = {"url1": 2}
    url_ranker.last_failed = {"url1": datetime.now().timestamp()}
    url_ranker.promote_url("url1")
    assert url_ranker.ranks["url1"] == 1
    assert "url1" not in url_ranker.last_failed

    url_ranker.promote_url("url_not_exist")
    assert url_ranker.ranks["url_not_exist"] == 0
    assert "url_not_exist" not in url_ranker.last_failed

    url_ranker.ranks = {"url2": 0}
    url_ranker.promote_url("url2")
    assert url_ranker.ranks["url2"] == 0  # Should not go below 0
