from bs4 import Tag
from datetime import timedelta
from urllib.parse import urljoin
from typing import override

from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.cache import CacheFeedExtension
from app.extensions.parsers.post_to_items import PostToItemsMixin


class AnilibriaFeed(PostToItemsMixin, SeleniumParserExtension, CacheFeedExtension):
    _cache_storage_time_if_success = timedelta(days=1)
    _cache_storage_time = timedelta(seconds=5)
    _selenium_wait_time = 5

    @property
    @override
    async def _posts(self) -> list[Tag]:
        soup = await self.get_soup(self.feed.url)
        alias = self._get_alias_from_url()
        episodes_container = self._find_episodes_container(soup, alias)
        return [
            a
            for a in episodes_container.find_all("a", class_="v-card")
            if isinstance(a, Tag)
        ]

    @override
    async def _get_post_title(self, post: Tag) -> str:
        soup = await self.get_soup(self.feed.url)
        show_title = self._extract_title(soup)
        episode_text = self._extract_episode_text(post)
        return f"{show_title} {episode_text}"

    @override
    async def _get_post_text(self, post: Tag) -> str:
        episode_text = self._extract_episode_text(post)
        episode_image_url = self._extract_episode_image_url(post)
        image_url = urljoin("https://anilibria.top", episode_image_url)
        return f'<img src="{image_url}" alt="episode"><br>{episode_text}'

    @override
    async def _get_post_link(self, post: Tag) -> str:
        episode_link = self._extract_episode_link(post)
        return urljoin("https://anilibria.top", episode_link)

    def _get_alias_from_url(self) -> str:
        return self.feed.url.strip("/").split("/")[-2]

    def _extract_title(self, soup: Tag) -> str:
        title_tag = soup.find("div", class_="text-autosize")
        if not (title_tag and isinstance(title_tag, Tag)):
            raise ValueError(
                "Could not extract title: <div class='text-autosize'> not found or not a Tag instance."
            )
        return title_tag.text.strip()

    def _find_episodes_container(self, soup: Tag, alias: str) -> Tag:
        episodes_container = soup.find("div", attrs={"alias": alias})
        if not (episodes_container and isinstance(episodes_container, Tag)):
            raise ValueError("Could not find episodes container.")
        return episodes_container

    def _extract_episode_text(self, episode_tag: Tag) -> str:
        episode_text_tag = episode_tag.find(
            "div", class_="fz-80 ff-heading font-weight-bold"
        )
        if not (episode_text_tag and isinstance(episode_text_tag, Tag)):
            raise ValueError("Could not extract episode text")

        return episode_text_tag.text.strip()

    def _extract_episode_link(self, episode_tag: Tag) -> str:
        if not (
            episode_tag
            and isinstance(episode_tag, Tag)
            and "href" in episode_tag.attrs
        ):
            raise ValueError("Could not extract episode link")

        return str(episode_tag["href"])

    def _extract_episode_image_url(self, episode_tag: Tag) -> str:
        img_tag = episode_tag.find("img", class_="v-img__img")
        if not (img_tag and isinstance(img_tag, Tag) and "src" in img_tag.attrs):
            raise ValueError("Could not extract episode image url")
        return str(img_tag["src"])
