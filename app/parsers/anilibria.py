from bs4 import Tag
from datetime import timedelta
from urllib.parse import urljoin

from app.serializers.feed import Item
from app.utils.datetime import constant_datetime
from app.extensions.parsers.selenium import SeleniumParserExtension
from app.extensions.parsers.cache import CacheFeedExtension


class AnilibriaFeed(SeleniumParserExtension, CacheFeedExtension):
    _cache_storage_time_if_success = timedelta(days=1)
    _cache_storage_time = timedelta(seconds=5)
    _selenium_wait_time = 5

    @property
    async def items(self) -> list[Item]:
        soup = await self.get_soup(self.feed.url)
        alias = self._get_alias_from_url()

        title = self._extract_title(soup)
        episodes_container = self._find_episodes_container(soup, alias)
        episodes = episodes_container.find_all("a", class_="v-card")
        items = []
        for episode in episodes:
            if not isinstance(episode, Tag):
                continue
            episode_text = self._extract_episode_text(episode)
            episode_link = self._extract_episode_link(episode)
            episode_image_url = self._extract_episode_image_url(episode)

            show_status = f"{title} {episode_text}"
            episode_url = urljoin("https://anilibria.top", episode_link)
            image_url = urljoin("https://anilibria.top", episode_image_url)
            text = f'<img src="{image_url}" alt="episode"><br>{episode_text}'

            items.append(
                Item(
                    title=show_status,
                    link=episode_url,
                    text=text,
                    date=constant_datetime,
                )
            )
        return items

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
