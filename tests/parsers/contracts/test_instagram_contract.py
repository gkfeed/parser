import base64
import json
from typing import cast
from urllib.parse import urlsplit, urlunsplit

import pytest
from aiohttp import web
from bs4 import BeautifulSoup, Tag
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from app.extensions.parsers.exceptions import FeedUnavailable
from app.parsers.instagram import AnonyigInstagramFeed, InstagramFeed
from app.serializers.feed import Feed
from app.services.http import HttpService
from app.services.selenium import SeleniumService


class BrowserElement(WebElement):
    """DOM-backed Selenium element, including the WebElement type contract."""

    def __init__(self, browser, node):
        self.browser = browser
        self.node = node

    def get_attribute(self, name):
        if name == "textContent":
            return self.node.get_text()
        value = self.node.get(name)
        return " ".join(value) if isinstance(value, list) else value

    def send_keys(self, *value: str) -> None:
        self.node["value"] = "".join(value)

    def is_displayed(self):
        return self.node.get("style") != "display:none"

    def find_elements(self, by=By.ID, value=None) -> list[WebElement]:
        return [BrowserElement(self.browser, node) for node in self.node.select(value)]


class AnonyigBrowser:
    """Search and observer pagination at the browser boundary, with a real DOM."""

    def __init__(self, batches, *, trigger=True):
        self.batches = list(batches)
        self.has_trigger = trigger
        self.scrolls = 0
        self.searched_username = None
        self.dom = BeautifulSoup(
            '<form class="search-form"><input class="search-form__input">'
            '<button class="search-form__button"></button></form>'
            '<div class="search-result" style="display:none">'
            '<div class="profile-media-list"></div></div>',
            "html.parser",
        )

    def find_elements(self, by, value):
        return [BrowserElement(self, node) for node in self.dom.select(value)]

    def find_element(self, by, value):
        elements = self.find_elements(by, value)
        if not elements:
            raise NoSuchElementException(value)
        return elements[0]

    def node(self, selector) -> Tag:
        node = self.dom.select_one(selector)
        assert isinstance(node, Tag), f"Fixture DOM is missing {selector}"
        return node

    def execute_script(self, script, element):
        if "scrollIntoView" in script:
            assert element.is_displayed()
            assert self.node(".search-result").get("style") != "display:none"
            self.scrolls += 1
            self.add_batch()
            return
        if "click" in script:
            self.searched_username = self.node("input").get("value")
            self.add_batch()
            return
        if "style.setProperty" in script:
            element.node.attrs.pop("style", None)
            return
        raise AssertionError(f"Unsupported browser action: {script}")

    def add_batch(self):
        if not self.batches:
            return
        urls = self.batches.pop(0)
        if urls is None:
            self.node(".trigger").decompose()
            return
        container = self.node(".profile-media-list")
        for url in urls:
            card = self.dom.new_tag("div", attrs={"class": "profile-media-list__item"})
            card.append(self.dom.new_tag("img", src=url))
            container.append(card)
        trigger = self.dom.select_one(".trigger")
        if self.has_trigger and trigger is None:
            container.append(self.dom.new_tag("div", attrs={"class": "trigger"}))


class FastAnonyigFeed(AnonyigInstagramFeed):
    # Immediate boundary transitions need no polling delay in deterministic tests.
    _load_more_wait_time = 0


@pytest.fixture
def anonyig_boundary(monkeypatch):
    def install(browser):
        async def get_html(args):
            args.make_actions_function(cast(WebDriver, browser))
            return str(browser.dom)

        monkeypatch.setattr(SeleniumService, "get_html", get_html)

    return install


def anonyig_parser():
    feed = Feed(
        id=1, title="Instagram", type="inst", url="https://www.instagram.test/@fixture/"
    )
    return FastAnonyigFeed(feed, {})


def embedded_sources(items):
    sources = []
    for item in items:
        image = BeautifulSoup(item.text, "html.parser").select_one("img")
        assert isinstance(image, Tag)
        sources.append(str(image["src"]))
    return sources


@pytest.mark.parametrize(
    ("batch_size", "expected_scrolls"), [(10, 2), (12, 2), (40, 0)]
)
async def test_anonyig_loads_more_until_media_cap(
    parser_site, anonyig_boundary, batch_size, expected_scrolls
):
    urls = [parser_site.image(number) for number in range(40)]
    browser = AnonyigBrowser(
        [urls[offset : offset + batch_size] for offset in range(0, 40, batch_size)]
    )
    anonyig_boundary(browser)
    parser = anonyig_parser()

    items = await parser.items

    assert len(items) == 30
    assert browser.scrolls == expected_scrolls
    assert browser.searched_username == "fixture"
    expected = [
        "data:image/png;base64," + base64.b64encode(body).decode()
        for body in list(parser_site.image_bodies.values())[:30]
    ]
    assert embedded_sources(items) == expected
    assert len(parser_site.requests) == 30
    assert all(item.title == "inst: fixture" for item in items)
    assert all(item.link == parser.feed.url for item in items)


async def test_anonyig_stops_when_trigger_is_absent(parser_site, anonyig_boundary):
    browser = AnonyigBrowser([[parser_site.image(1)]], trigger=False)
    anonyig_boundary(browser)

    items = await anonyig_parser().items

    assert len(items) == 1
    assert browser.scrolls == 0


async def test_anonyig_stops_when_trigger_disappears(parser_site, anonyig_boundary):
    urls = [parser_site.image(number) for number in range(2)]
    browser = AnonyigBrowser([urls, None])
    anonyig_boundary(browser)

    items = await anonyig_parser().items

    assert len(items) == 2
    assert browser.scrolls == 1
    assert browser.dom.select_one(".trigger") is None


async def test_anonyig_no_new_media_raises_instead_of_returning_partial_results(
    parser_site, anonyig_boundary
):
    browser = AnonyigBrowser([[parser_site.image(1)], []])
    anonyig_boundary(browser)

    with pytest.raises(FeedUnavailable, match="media_loading_timeout"):
        await anonyig_parser().items

    assert browser.scrolls == 1
    assert parser_site.requests == []


async def test_anonyig_image_requests_overlap_and_all_images_are_returned(
    parser_site, anonyig_boundary
):
    parser_site.require_image_overlap = True
    urls = [parser_site.image(number) for number in range(8)]
    anonyig_boundary(AnonyigBrowser([urls], trigger=False))

    items = await anonyig_parser().items

    assert parser_site.peak_images > 1
    assert len(items) == len(urls)
    assert len(set(embedded_sources(items))) == len(urls)
    assert sorted(parser_site.requests) == sorted(parser_site.image_bodies)


@pytest.fixture
def instagram_http_boundary(monkeypatch, parser_site):
    get_response = HttpService.get_response

    async def local_response(url, **kwargs):
        parsed = urlsplit(url)
        if parsed.hostname == "www.instagram.com":
            origin = urlsplit(parser_site.url)
            url = urlunsplit(
                (origin.scheme, origin.netloc, parsed.path, parsed.query, "")
            )
        else:
            assert parsed.netloc == urlsplit(parser_site.url).netloc
        return await get_response(url, **kwargs)

    monkeypatch.setattr(HttpService, "get_response", local_response)


def crawler_page(urls):
    user = {
        "id": "123",
        "username": "fixture",
        "is_private": False,
        "polaris_timeline_connection": {
            "count": len(urls),
            "edges": [
                {"node": {"shortcode": f"post{n}", "display_url": url}}
                for n, url in enumerate(urls)
            ],
        },
    }
    return web.Response(
        text=f'<script type="application/json">{json.dumps(user)}</script>',
        content_type="text/html",
    )


def embed_parser():
    return InstagramFeed(
        Feed(
            id=1,
            title="Instagram",
            type="inst",
            url="https://www.instagram.com/fixture/",
        ),
        {},
    )


@pytest.mark.parametrize("count", [2, 35])
async def test_runtime_inst_embeds_images_and_respects_media_cap(
    parser_site, instagram_http_boundary, count
):
    urls = [parser_site.image(number) for number in range(count)]
    parser_site.pages["/fixture/"] = crawler_page(urls)

    items = await embed_parser().items

    assert len(items) == min(count, 30)
    assert [item.link for item in items] == [
        f"https://www.instagram.com/p/post{n}/" for n in range(min(count, 30))
    ]
    assert embedded_sources(items) == [
        "data:image/png;base64," + base64.b64encode(body).decode()
        for body in list(parser_site.image_bodies.values())[:30]
    ]
    assert all(item.title == "inst: fixture" for item in items)
    assert len(parser_site.requests) == 1 + min(count, 30)


async def test_runtime_inst_rejects_image_http_failure(
    parser_site, instagram_http_boundary
):
    parser_site.pages["/fixture/"] = crawler_page([f"{parser_site.url}/broken.png"])
    parser_site.pages["/broken.png"] = web.Response(status=503, text="Unavailable")

    with pytest.raises(FeedUnavailable, match="invalid_image_response"):
        await embed_parser().items
