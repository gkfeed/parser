"""Local source pages and instance dependencies for the real Stories parser."""

from app.parsers.stories.selenium import InstagramStoriesFeed
from app.serializers.feed import Feed
from app.services.cache.storage.memory import MemoryStorage
from app.services.cache.temporary import TemporaryCacheService
from tests.browser.resources import LocalChromium

FORM = """<form class="search-form" onsubmit="return false">
<input class="search-form__input">
<button class="search-form__button" type="submit">Search</button></form>"""


def result(body: str) -> str:
    return FORM + f'<section class="search-result">{body}</section>'


def media(url: str, *, trigger: str = '<div class="trigger">More</div>') -> str:
    return result(f'''
<button class="tabs-component__button tabs-component__button--active">Stories</button>
<div class="profile-media-list">
<article class="profile-media-list__item">
<a class="download-btn" href="{url}/video.mp4">Download</a>
</article>{trigger}</div>''')


def stories_parser(url: str, browser: LocalChromium) -> InstagramStoriesFeed:
    parser = InstagramStoriesFeed(
        Feed(id=2, title="Local", type="stories", url=url), {}
    )
    parser._service_url = url
    parser._selenium_wait_time = 0
    parser._results_wait_time = 0
    parser.selenium_driver_factory = browser
    parser.cache = TemporaryCacheService(storage=MemoryStorage())
    return parser
